"""Pure stdlib lstat-only probe for P2 owner exact WSL root metadata verification."""

from __future__ import annotations

import os
import stat
import time
from typing import Any

from .config import (
    ADDITIONAL_TARGETS,
    ANCESTOR_CHAIN,
    APPROVED_MONTH_PARTITIONS,
    DEFAULT_OWNER_WSL_DATA_ROOT,
    MAX_LSTAT,
    MAX_SELECTED_DIR_ENTRIES,
    MAX_SELECTED_DIR_LIST,
    AdditionalTargetObservation,
    AncestorStat,
    FilePresenceStatus,
    MonthPartitionObservation,
    ResourceCounters,
    TerminalVerdict,
    is_path_protected,
    is_path_traversal,
)


class ProbeSecurityError(RuntimeError):
    """Raised when an unauthorized or protected path access is attempted."""


class ProbeBudgetExceededError(RuntimeError):
    """Raised when any hard execution cap is exceeded."""


class OwnerRootProbe:
    """Read-only, lstat-only metadata probe enforcing strict caps and positive whitelist."""

    def __init__(
        self,
        data_root: str = DEFAULT_OWNER_WSL_DATA_ROOT,
        max_lstat: int = MAX_LSTAT,
        max_dir_lists: int = MAX_SELECTED_DIR_LIST,
        max_dir_entries: int = MAX_SELECTED_DIR_ENTRIES,
    ) -> None:
        self.data_root = os.path.abspath(data_root)
        self.max_lstat = max_lstat
        self.max_dir_lists = max_dir_lists
        self.max_dir_entries = max_dir_entries

        self.counters = ResourceCounters()
        self.ancestor_observations: list[AncestorStat] = []
        self.month_observations: list[MonthPartitionObservation] = []
        self.target_observations: list[AdditionalTargetObservation] = []
        self.terminal_verdict: TerminalVerdict = TerminalVerdict.BLOCKED_NOT_PUSHED
        self.stop_reason: str | None = None
        self._start_time: float = 0.0

    def _safe_lstat(self, path: str) -> os.stat_result:
        """Perform os.lstat with cap checks, traversal rejection, and protected pattern rejection."""
        if self.counters.lstat_calls >= self.max_lstat:
            raise ProbeBudgetExceededError(
                f"MAX_LSTAT cap ({self.max_lstat}) reached at {self.counters.lstat_calls} calls"
            )

        if is_path_traversal(path):
            self.counters.protected_body_or_partition_accesses += 1
            raise ProbeSecurityError(f"Directory traversal detected in path: {path}")

        if is_path_protected(path):
            self.counters.protected_body_or_partition_accesses += 1
            raise ProbeSecurityError(f"Protected holdout/excluded path pattern detected: {path}")

        self.counters.lstat_calls += 1
        return os.lstat(path)

    def verify_ancestors(self, custom_chain: list[str] | None = None) -> bool:
        """Verify non-symlink ancestor chain from /root down to research/BTCUSDT."""
        chain = custom_chain if custom_chain is not None else ANCESTOR_CHAIN
        all_ok = True

        for ancestor in chain:
            obs = AncestorStat(path=ancestor)
            try:
                st = self._safe_lstat(ancestor)
                obs.exists = True
                obs.is_symlink = stat.S_ISLNK(st.st_mode)
                obs.is_dir = stat.S_ISDIR(st.st_mode)
                obs.mode_octal = oct(st.st_mode)
                obs.dev = int(st.st_dev)
                obs.ino = int(st.st_ino)

                if obs.is_symlink:
                    self.counters.symlinks_encountered += 1
                    obs.error = "SYMLINK_REJECTED: ancestor path cannot be a symbolic link"
                    all_ok = False
            except FileNotFoundError:
                obs.exists = False
                obs.error = "ENOENT: ancestor directory does not exist"
                all_ok = False
            except Exception as e:
                obs.exists = False
                obs.error = f"{type(e).__name__}: {e}"
                all_ok = False

            self.ancestor_observations.append(obs)

        return all_ok

    def scan_selected_months(self) -> None:
        """Scan precisely the 6 approved nonprotected month partitions."""
        for part in APPROVED_MONTH_PARTITIONS:
            label = part["label"]
            year = part["year"]
            month = part["month"]
            rel_dir = part["rel_dir"]
            full_dir = os.path.join(self.data_root, rel_dir)

            obs = MonthPartitionObservation(
                label=label,
                year=year,
                month=month,
                rel_dir=rel_dir,
            )

            # 1. Check directory existence via lstat
            try:
                dir_st = self._safe_lstat(full_dir)
                obs.dir_exists = True
                obs.dir_is_symlink = stat.S_ISLNK(dir_st.st_mode)

                if obs.dir_is_symlink:
                    self.counters.symlinks_encountered += 1
                    obs.status = FilePresenceStatus.SYMLINK_REJECTED.value
                    obs.notes = "Partition directory is an unauthorized symlink"
                    self.month_observations.append(obs)
                    continue

                if not stat.S_ISDIR(dir_st.st_mode):
                    obs.notes = "Partition path exists but is not a directory"
                    self.month_observations.append(obs)
                    continue

            except FileNotFoundError:
                obs.dir_exists = False
                obs.status = FilePresenceStatus.ENOENT.value
                obs.notes = f"Directory not found: {rel_dir}"
                self.month_observations.append(obs)
                continue
            except ProbeSecurityError as e:
                obs.status = FilePresenceStatus.PROTECTED_EXCLUDED.value
                obs.notes = f"Security rejection: {e}"
                self.month_observations.append(obs)
                continue

            # 2. Check exact default file `data.parquet` first
            default_file_rel = f"{rel_dir}/data.parquet"
            default_file_full = os.path.join(self.data_root, default_file_rel)

            try:
                file_st = self._safe_lstat(default_file_full)
                obs.file_name = "data.parquet"
                obs.file_rel_path = default_file_rel
                obs.file_exists = True
                obs.file_is_symlink = stat.S_ISLNK(file_st.st_mode)
                obs.file_is_regular = stat.S_ISREG(file_st.st_mode)
                obs.file_size_bytes = int(file_st.st_size)
                obs.file_mode_octal = oct(file_st.st_mode)
                obs.file_mtime = float(file_st.st_mtime)

                if obs.file_is_symlink:
                    self.counters.symlinks_encountered += 1
                    obs.status = FilePresenceStatus.SYMLINK_REJECTED.value
                    obs.notes = "Parquet file is a symlink (disallowed)"
                elif obs.file_is_regular:
                    obs.status = FilePresenceStatus.PRESENT_METADATA_ONLY.value
                    obs.notes = "Exact data.parquet located; metadata only, zero body bytes read"
                else:
                    obs.status = FilePresenceStatus.DIRECTORY_PRESENT_FILE_NAME_UNKNOWN.value
                    obs.notes = "data.parquet present but not a regular file"

                self.month_observations.append(obs)
                continue

            except FileNotFoundError:
                # Default name missing; check if parquet basename differs via strictly capped scandir
                pass
            except ProbeSecurityError as e:
                obs.status = FilePresenceStatus.PROTECTED_EXCLUDED.value
                obs.notes = f"Security rejection on default file: {e}"
                self.month_observations.append(obs)
                continue

            # 3. If data.parquet missing, scandir only this approved directory (cap <= 16 entries)
            if self.counters.dir_list_calls >= self.max_dir_lists:
                obs.status = FilePresenceStatus.DIRECTORY_PRESENT_FILE_NAME_UNKNOWN.value
                obs.notes = "MAX_SELECTED_DIR_LIST limit reached; cannot scandir month directory"
                self.month_observations.append(obs)
                continue

            self.counters.dir_list_calls += 1
            found_parquet = None
            scanned_entries = 0

            try:
                with os.scandir(full_dir) as it:
                    for entry in it:
                        scanned_entries += 1
                        self.counters.dir_entries_scanned += 1
                        if scanned_entries > self.max_dir_entries:
                            break

                        if entry.name.endswith(".parquet"):
                            # lstat regular name
                            try:
                                entry_st = self._safe_lstat(entry.path)
                                if stat.S_ISREG(entry_st.st_mode) and not stat.S_ISLNK(entry_st.st_mode):
                                    found_parquet = (entry.name, entry.path, entry_st)
                                    break
                            except Exception:
                                pass

                if found_parquet:
                    name, full_p, st = found_parquet
                    obs.file_name = name
                    obs.file_rel_path = f"{rel_dir}/{name}"
                    obs.file_exists = True
                    obs.file_is_regular = True
                    obs.file_size_bytes = int(st.st_size)
                    obs.file_mode_octal = oct(st.st_mode)
                    obs.file_mtime = float(st.st_mtime)
                    obs.status = FilePresenceStatus.PRESENT_METADATA_ONLY.value
                    obs.notes = (
                        f"Alternate parquet name {name} located via capped scandir; zero body bytes read"
                    )
                else:
                    obs.status = FilePresenceStatus.DIRECTORY_PRESENT_FILE_NAME_UNKNOWN.value
                    obs.notes = "Directory present, but no valid .parquet file located"

            except Exception as e:
                obs.status = FilePresenceStatus.DIRECTORY_PRESENT_FILE_NAME_UNKNOWN.value
                obs.notes = f"Error during capped scandir: {e}"

            self.month_observations.append(obs)

    def scan_additional_targets(self) -> None:
        """Scan additional exact parent directories and metadata files (NO OPEN)."""
        for item in ADDITIONAL_TARGETS:
            rel_path = item["rel_path"]
            full_path = os.path.join(self.data_root, rel_path)

            obs = AdditionalTargetObservation(
                target_id=item["target_id"],
                rel_path=rel_path,
                expected_type=item["expected_type"],
                role=item["role"],
                proves_minute_pit=item["proves_minute_pit"],
                is_spot=item["is_spot"],
            )

            try:
                st = self._safe_lstat(full_path)
                obs.exists = True
                obs.is_symlink = stat.S_ISLNK(st.st_mode)
                obs.is_dir = stat.S_ISDIR(st.st_mode)
                obs.is_regular = stat.S_ISREG(st.st_mode)
                obs.size_bytes = int(st.st_size)
                obs.mode_octal = oct(st.st_mode)

                if obs.is_symlink:
                    self.counters.symlinks_encountered += 1
                    obs.status = FilePresenceStatus.SYMLINK_REJECTED.value
                    obs.notes = "Target is a symlink (disallowed)"
                elif item["expected_type"] == "dir" and obs.is_dir:
                    obs.status = FilePresenceStatus.PRESENT_METADATA_ONLY.value
                    obs.notes = (
                        "Parent directory exists; existence does NOT prove continuous true 1m PIT or valid clock"
                    )
                elif item["expected_type"] == "file" and obs.is_regular:
                    obs.status = FilePresenceStatus.PRESENT_METADATA_ONLY.value
                    obs.notes = "Metadata file exists; stat-only, no contents opened"
                else:
                    obs.status = FilePresenceStatus.DIRECTORY_PRESENT_FILE_NAME_UNKNOWN.value
                    obs.notes = f"Type mismatch: expected {item['expected_type']}"

            except FileNotFoundError:
                obs.exists = False
                obs.status = FilePresenceStatus.ENOENT.value
                obs.notes = "Target not found at exact path"
            except ProbeSecurityError as e:
                obs.status = FilePresenceStatus.PROTECTED_EXCLUDED.value
                obs.notes = f"Security rejection: {e}"

            self.target_observations.append(obs)

    def execute(self) -> TerminalVerdict:
        """Run full verification pipeline deterministically."""
        self._start_time = time.time()

        # Check data root existence
        if not os.path.exists(self.data_root):
            self.terminal_verdict = TerminalVerdict.P2_OWNER_ROOT_NOT_PRESENT_AT_EXACT_PATH
            self.stop_reason = f"Owner data root not present at exact path: {self.data_root}"
            self.counters.wall_clock_seconds = time.time() - self._start_time
            return self.terminal_verdict

        # Verify ancestor chain
        ancestors_ok = self.verify_ancestors()
        if not ancestors_ok:
            # Check if failure was symlink vs missing
            has_symlink = any(a.is_symlink for a in self.ancestor_observations)
            if has_symlink:
                self.terminal_verdict = TerminalVerdict.P2_PROTECTION_OR_IDENTITY_STOP
                self.stop_reason = "Symlink detected in ancestor path hierarchy"
                self.counters.wall_clock_seconds = time.time() - self._start_time
                return self.terminal_verdict
            else:
                self.terminal_verdict = TerminalVerdict.P2_OWNER_ROOT_NOT_PRESENT_AT_EXACT_PATH
                self.stop_reason = "One or more ancestor paths failed to resolve"
                self.counters.wall_clock_seconds = time.time() - self._start_time
                return self.terminal_verdict

        # Scan selected months
        self.scan_selected_months()

        # Scan additional targets
        self.scan_additional_targets()

        self.counters.wall_clock_seconds = time.time() - self._start_time

        # Check for any protection stop
        if any(m.status == FilePresenceStatus.SYMLINK_REJECTED.value for m in self.month_observations) or any(
            t.status == FilePresenceStatus.SYMLINK_REJECTED.value for t in self.target_observations
        ):
            self.terminal_verdict = TerminalVerdict.P2_PROTECTION_OR_IDENTITY_STOP
            self.stop_reason = "Symlink detected in evaluated targets"
            return self.terminal_verdict

        # Determine if all 6 selected months are PRESENT_METADATA_ONLY
        all_6_present = len(self.month_observations) == 6 and all(
            m.status == FilePresenceStatus.PRESENT_METADATA_ONLY.value for m in self.month_observations
        )

        if all_6_present:
            self.terminal_verdict = TerminalVerdict.P2_BTC_SELECTED_NONPROTECTED_FILES_LOCATED_METADATA_ONLY
            self.stop_reason = (
                "All 6 approved nonprotected BTC month parquet files located via exact metadata-only lstat."
            )
        else:
            self.terminal_verdict = TerminalVerdict.P2_OWNER_ROOT_PRESENT_BUT_SELECTED_FILES_INCOMPLETE
            missing_labels = [
                m.label for m in self.month_observations if m.status != FilePresenceStatus.PRESENT_METADATA_ONLY.value
            ]
            self.stop_reason = f"Selected month files incomplete: {missing_labels}"

        return self.terminal_verdict
