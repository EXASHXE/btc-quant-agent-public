"""Pure stdlib lstat-only probe for P2 owner exact WSL root metadata verification."""

from __future__ import annotations

import os
import stat
import time

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
    """Raised when an unauthorized, symlink, or protected path access is attempted."""


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
        allow_custom_root: bool = False,
    ) -> None:
        self.allow_custom_root = allow_custom_root
        clean_root = os.path.abspath(data_root)

        # Enforce authorized owner root unless explicit test mode is granted
        if not self.allow_custom_root and clean_root != DEFAULT_OWNER_WSL_DATA_ROOT:
            raise ProbeSecurityError(
                f"Unauthorized data root: {clean_root}. In production only "
                f"{DEFAULT_OWNER_WSL_DATA_ROOT} is authorized."
            )

        self.data_root = clean_root
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
        self._verified_non_symlink_components: set[str] = set()

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

    def _verify_path_components_non_symlink(self, rel_path: str) -> str:
        """Walk and verify every intermediate component of a relative path under data_root."""
        # Detect traversal or protected patterns before splitting
        if is_path_traversal(rel_path):
            self.counters.protected_body_or_partition_accesses += 1
            raise ProbeSecurityError(f"Directory traversal detected in relative path: {rel_path}")

        if is_path_protected(rel_path):
            self.counters.protected_body_or_partition_accesses += 1
            raise ProbeSecurityError(f"Protected path pattern detected in relative path: {rel_path}")

        full_target = os.path.abspath(os.path.join(self.data_root, rel_path))

        # Check mount/root escape via commonpath (prevent prefix tricks like data-v2)
        try:
            common = os.path.commonpath([self.data_root, full_target])
            if common != self.data_root:
                self.counters.protected_body_or_partition_accesses += 1
                raise ProbeSecurityError(f"Path escapes authorized data root: {full_target}")
        except ValueError as err:
            self.counters.protected_body_or_partition_accesses += 1
            raise ProbeSecurityError(f"Path escape attempt across drives/roots: {err}") from err

        # Verify intermediate components from data_root down to target
        rel_parts = os.path.relpath(full_target, self.data_root).split(os.sep)
        curr = self.data_root
        for part in rel_parts:
            curr = os.path.join(curr, part)
            if curr not in self._verified_non_symlink_components:
                st = self._safe_lstat(curr)
                if stat.S_ISLNK(st.st_mode):
                    self.counters.symlinks_encountered += 1
                    raise ProbeSecurityError(f"Symlink detected at intermediate component: {curr}")
                self._verified_non_symlink_components.add(curr)

        return full_target

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
            except PermissionError as e:
                obs.exists = False
                obs.error = f"PERMISSION_DENIED: {e}"
                all_ok = False
            except (ProbeSecurityError, ProbeBudgetExceededError):
                raise
            except OSError as e:
                obs.exists = False
                obs.error = f"OSError: {e}"
                all_ok = False

            self.ancestor_observations.append(obs)

        return all_ok

    def scan_selected_months(self) -> None:
        """Scan precisely the 6 approved nonprotected month partitions with intermediate symlink checks."""
        for part in APPROVED_MONTH_PARTITIONS:
            label = part["label"]
            year = part["year"]
            month = part["month"]
            rel_dir = part["rel_dir"]

            obs = MonthPartitionObservation(
                label=label,
                year=year,
                month=month,
                rel_dir=rel_dir,
            )

            # 1. Verify directory and intermediate path components
            try:
                full_dir = self._verify_path_components_non_symlink(rel_dir)
                dir_st = os.lstat(full_dir)
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
            except PermissionError as e:
                obs.dir_exists = False
                obs.status = FilePresenceStatus.PERMISSION_DENIED.value
                obs.notes = f"Permission denied accessing directory {rel_dir}: {e}"
                self.month_observations.append(obs)
                continue
            except ProbeSecurityError as e:
                if "Symlink" in str(e):
                    obs.status = FilePresenceStatus.SYMLINK_REJECTED.value
                else:
                    obs.status = FilePresenceStatus.PROTECTED_EXCLUDED.value
                obs.notes = f"Security rejection: {e}"
                self.month_observations.append(obs)
                continue
            except ProbeBudgetExceededError:
                raise

            # 2. Check exact default file `data.parquet` first
            default_file_rel = f"{rel_dir}/data.parquet"
            try:
                default_file_full = self._verify_path_components_non_symlink(default_file_rel)
                file_st = os.lstat(default_file_full)
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
            except PermissionError as e:
                obs.status = FilePresenceStatus.PERMISSION_DENIED.value
                obs.notes = f"Permission denied accessing default parquet: {e}"
                self.month_observations.append(obs)
                continue
            except ProbeSecurityError as e:
                if "Symlink" in str(e):
                    obs.status = FilePresenceStatus.SYMLINK_REJECTED.value
                else:
                    obs.status = FilePresenceStatus.PROTECTED_EXCLUDED.value
                obs.notes = f"Security rejection on default file: {e}"
                self.month_observations.append(obs)
                continue
            except ProbeBudgetExceededError:
                raise

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
                            # Validate entry name does not contain traversal or protected patterns
                            if is_path_traversal(entry.name) or is_path_protected(entry.name):
                                self.counters.protected_body_or_partition_accesses += 1
                                raise ProbeSecurityError(
                                    f"Malicious parquet filename in directory: {entry.name}"
                                )

                            try:
                                entry_st = self._safe_lstat(entry.path)
                                if stat.S_ISLNK(entry_st.st_mode):
                                    self.counters.symlinks_encountered += 1
                                    raise ProbeSecurityError(
                                        f"Symlink parquet found in alternate lookup: {entry.name}"
                                    )
                                if stat.S_ISREG(entry_st.st_mode):
                                    found_parquet = (entry.name, entry.path, entry_st)
                                    break
                            except FileNotFoundError:
                                continue
                            except (ProbeSecurityError, ProbeBudgetExceededError):
                                raise

                if found_parquet:
                    name, _full_p, st = found_parquet
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

            except (ProbeSecurityError, ProbeBudgetExceededError):
                raise
            except PermissionError as e:
                obs.status = FilePresenceStatus.PERMISSION_DENIED.value
                obs.notes = f"Permission denied during scandir: {e}"
            except OSError as e:
                obs.status = FilePresenceStatus.DIRECTORY_PRESENT_FILE_NAME_UNKNOWN.value
                obs.notes = f"Error during capped scandir: {e}"

            self.month_observations.append(obs)

    def scan_additional_targets(self) -> None:
        """Scan additional exact parent directories and metadata files (NO OPEN)."""
        for item in ADDITIONAL_TARGETS:
            rel_path = item["rel_path"]

            obs = AdditionalTargetObservation(
                target_id=item["target_id"],
                rel_path=rel_path,
                expected_type=item["expected_type"],
                role=item["role"],
                proves_minute_pit=item["proves_minute_pit"],
                is_spot=item["is_spot"],
            )

            try:
                full_path = self._verify_path_components_non_symlink(rel_path)
                st = os.lstat(full_path)
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
            except PermissionError as e:
                obs.exists = False
                obs.status = FilePresenceStatus.PERMISSION_DENIED.value
                obs.notes = f"Permission denied accessing target {rel_path}: {e}"
            except ProbeSecurityError as e:
                if "Symlink" in str(e):
                    obs.status = FilePresenceStatus.SYMLINK_REJECTED.value
                else:
                    obs.status = FilePresenceStatus.PROTECTED_EXCLUDED.value
                obs.notes = f"Security rejection: {e}"
            except ProbeBudgetExceededError:
                raise

            self.target_observations.append(obs)

    def execute(self) -> TerminalVerdict:
        """Run full verification pipeline deterministically."""
        self._start_time = time.time()

        # Check data root existence using safe lstat (do not follow symlinks)
        try:
            root_st = self._safe_lstat(self.data_root)
            if stat.S_ISLNK(root_st.st_mode):
                self.counters.symlinks_encountered += 1
                self.terminal_verdict = TerminalVerdict.P2_PROTECTION_OR_IDENTITY_STOP
                self.stop_reason = f"Owner data root is a symbolic link: {self.data_root}"
                self.counters.wall_clock_seconds = time.time() - self._start_time
                return self.terminal_verdict
            if not stat.S_ISDIR(root_st.st_mode):
                self.terminal_verdict = TerminalVerdict.P2_OWNER_ROOT_NOT_PRESENT_AT_EXACT_PATH
                self.stop_reason = f"Owner data root exists but is not a directory: {self.data_root}"
                self.counters.wall_clock_seconds = time.time() - self._start_time
                return self.terminal_verdict
            self._verified_non_symlink_components.add(self.data_root)
        except FileNotFoundError:
            self.terminal_verdict = TerminalVerdict.P2_OWNER_ROOT_NOT_PRESENT_AT_EXACT_PATH
            self.stop_reason = f"Owner data root not present at exact path: {self.data_root}"
            self.counters.wall_clock_seconds = time.time() - self._start_time
            return self.terminal_verdict
        except PermissionError as e:
            self.terminal_verdict = TerminalVerdict.P2_OWNER_ROOT_NOT_PRESENT_AT_EXACT_PATH
            self.stop_reason = f"Permission denied accessing data root: {e}"
            self.counters.wall_clock_seconds = time.time() - self._start_time
            return self.terminal_verdict
        except ProbeSecurityError as e:
            self.terminal_verdict = TerminalVerdict.P2_PROTECTION_OR_IDENTITY_STOP
            self.stop_reason = f"Security violation on data root: {e}"
            self.counters.wall_clock_seconds = time.time() - self._start_time
            return self.terminal_verdict

        # Verify ancestor chain
        try:
            ancestors_ok = self.verify_ancestors()
        except ProbeSecurityError as e:
            self.terminal_verdict = TerminalVerdict.P2_PROTECTION_OR_IDENTITY_STOP
            self.stop_reason = f"Security violation in ancestor chain: {e}"
            self.counters.wall_clock_seconds = time.time() - self._start_time
            return self.terminal_verdict

        if not ancestors_ok:
            has_symlink = any(a.is_symlink for a in self.ancestor_observations)
            if has_symlink:
                self.terminal_verdict = TerminalVerdict.P2_PROTECTION_OR_IDENTITY_STOP
                self.stop_reason = "Symlink detected in ancestor path hierarchy"
            else:
                self.terminal_verdict = TerminalVerdict.P2_OWNER_ROOT_NOT_PRESENT_AT_EXACT_PATH
                self.stop_reason = "One or more ancestor paths failed to resolve"
            self.counters.wall_clock_seconds = time.time() - self._start_time
            return self.terminal_verdict

        # Scan selected months
        try:
            self.scan_selected_months()
        except ProbeSecurityError as e:
            self.terminal_verdict = TerminalVerdict.P2_PROTECTION_OR_IDENTITY_STOP
            self.stop_reason = f"Security violation in month scan: {e}"
            self.counters.wall_clock_seconds = time.time() - self._start_time
            return self.terminal_verdict

        # Scan additional targets
        try:
            self.scan_additional_targets()
        except ProbeSecurityError as e:
            self.terminal_verdict = TerminalVerdict.P2_PROTECTION_OR_IDENTITY_STOP
            self.stop_reason = f"Security violation in target scan: {e}"
            self.counters.wall_clock_seconds = time.time() - self._start_time
            return self.terminal_verdict

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
