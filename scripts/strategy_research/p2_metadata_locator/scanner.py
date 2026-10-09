"""Bounded, safe metadata-only filesystem scanner and root candidate locator."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any

from scripts.strategy_research.p2_metadata_locator.config import (
    DECLARED_BTC_MANIFEST_PARTITIONS,
    DEFAULT_CANDIDATE_ROOTS,
    FORBIDDEN_PROJECT_SUBDIRS,
    FORBIDDEN_ROOTS,
    MAX_DEPTH,
    MAX_DIR_ENTRIES,
    MAX_LSTAT,
    MAX_SELECTED_PARTITION_LSTAT,
    MAX_WALL_CLOCK_SECONDS,
    SELECTED_SAFE_MONTHS,
    CoverageStatus,
    RootCertainty,
    ScanCounters,
    TerminalVerdict,
    is_path_protected_holdout,
)


@dataclass
class PartitionProbeResult:
    month: str
    relative_path: str
    declared_sha256: str
    physical_exists: bool
    lstat_size_bytes: int | None = None
    lstat_mtime: float | None = None
    status: CoverageStatus = CoverageStatus.UNKNOWN_UNPROBED
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "month": self.month,
            "relative_path": self.relative_path,
            "declared_sha256": self.declared_sha256,
            "physical_exists": self.physical_exists,
            "lstat_size_bytes": self.lstat_size_bytes,
            "lstat_mtime": self.lstat_mtime,
            "status": self.status.value if isinstance(self.status, CoverageStatus) else str(self.status),
            "reason": self.reason,
        }


@dataclass
class CandidateEvaluation:
    candidate_root: str
    exists: bool
    is_symlink: bool
    is_dir: bool
    ownership_authorized: bool
    rejection_reason: str | None = None
    subdirectories_found: list[str] = field(default_factory=list)
    market_like_indicators: list[str] = field(default_factory=list)
    safe_partitions_checked: dict[str, PartitionProbeResult] = field(default_factory=dict)
    certainty: RootCertainty = RootCertainty.ROOT_UNKNOWN

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_root": self.candidate_root,
            "exists": self.exists,
            "is_symlink": self.is_symlink,
            "is_dir": self.is_dir,
            "ownership_authorized": self.ownership_authorized,
            "rejection_reason": self.rejection_reason,
            "subdirectories_found": self.subdirectories_found[:50],
            "market_like_indicators": self.market_like_indicators,
            "safe_partitions_checked": {
                k: v.to_dict() for k, v in self.safe_partitions_checked.items()
            },
            "certainty": self.certainty.value if isinstance(self.certainty, RootCertainty) else str(self.certainty),
        }


@dataclass
class ScanExecutionReceipt:
    task_id: str
    start_time_iso: str
    end_time_iso: str
    duration_seconds: float
    counters: ScanCounters
    evaluated_roots: list[CandidateEvaluation]
    confirmed_root: str | None
    terminal_verdict: TerminalVerdict
    budget_exhausted: bool = False
    stop_reason: str | None = None
    one_owner_request: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "start_time_iso": self.start_time_iso,
            "end_time_iso": self.end_time_iso,
            "duration_seconds": self.duration_seconds,
            "counters": self.counters.to_dict(),
            "evaluated_roots": [e.to_dict() for e in self.evaluated_roots],
            "confirmed_root": self.confirmed_root,
            "terminal_verdict": self.terminal_verdict.value if isinstance(self.terminal_verdict, TerminalVerdict) else str(self.terminal_verdict),
            "budget_exhausted": self.budget_exhausted,
            "stop_reason": self.stop_reason,
            "one_owner_request": self.one_owner_request,
        }


class MetadataScanner:
    """Bounded metadata scanner strictly observing security and safety caps."""

    def __init__(
        self,
        candidate_roots: list[str] | None = None,
        max_depth: int = MAX_DEPTH,
        max_dir_entries: int = MAX_DIR_ENTRIES,
        max_lstat: int = MAX_LSTAT,
        max_selected_partition_lstat: int = MAX_SELECTED_PARTITION_LSTAT,
        max_wall_clock_seconds: float = MAX_WALL_CLOCK_SECONDS,
        allowed_root_prefixes: list[str] | None = None,
    ) -> None:
        self.candidate_roots = candidate_roots or list(DEFAULT_CANDIDATE_ROOTS)
        self.max_depth = max_depth
        self.max_dir_entries = max_dir_entries
        self.max_lstat = max_lstat
        self.max_selected_partition_lstat = max_selected_partition_lstat
        self.max_wall_clock_seconds = max_wall_clock_seconds
        self.allowed_root_prefixes = allowed_root_prefixes

        self.counters = ScanCounters()
        self.start_time: float = time.time()
        self.stop_reason: str | None = None
        self.budget_exhausted: bool = False

    def _safe_lstat(self, path: str) -> os.stat_result | None:
        """Perform a single lstat while strictly tracking lstat budget and zero body reads."""
        if self.counters.lstat_calls >= self.max_lstat:
            self.stop_reason = f"LSTAT_CAP_REACHED_{self.max_lstat}"
            self.budget_exhausted = True
            return None

        if time.time() - self.start_time > self.max_wall_clock_seconds:
            self.stop_reason = f"WALL_CLOCK_TIMEOUT_{self.max_wall_clock_seconds}s"
            self.budget_exhausted = True
            return None

        self.counters.lstat_calls += 1
        try:
            return os.lstat(path)
        except (FileNotFoundError, NotADirectoryError):
            return None
        except PermissionError:
            self.counters.permission_denied_entries += 1
            return None
        except OSError:
            return None

    def _is_forbidden_root(self, path: str) -> tuple[bool, str]:
        """Check if root is forbidden or tries to escape allowlist."""
        norm = os.path.realpath(path) if os.path.exists(path) else os.path.abspath(path)
        if norm in FORBIDDEN_ROOTS or path in FORBIDDEN_ROOTS:
            return True, f"FORBIDDEN_ROOT_{path}"

        for fb in FORBIDDEN_ROOTS:
            if norm == fb:
                return True, f"FORBIDDEN_ROOT_MATCH_{fb}"

        # If allowed prefixes are specified, ensure candidate starts with one
        if self.allowed_root_prefixes:
            matched = any(norm.startswith(p) or path.startswith(p) for p in self.allowed_root_prefixes)
            if not matched:
                return True, f"NOT_IN_ALLOWED_PREFIXES_{self.allowed_root_prefixes}"

        return False, ""

    def _is_foreign_or_protected_entry(self, entry_name: str, full_path: str) -> tuple[bool, str]:
        """Check if an entry is hidden, forbidden foreign repo, or protected holdout."""
        if entry_name.startswith("."):
            self.counters.hidden_paths_skipped += 1
            return True, "HIDDEN_ENTRY"

        if entry_name in FORBIDDEN_PROJECT_SUBDIRS:
            return True, f"FORBIDDEN_PROJECT_SUBDIR_{entry_name}"

        # Never enter other git repositories
        if os.path.lexists(os.path.join(full_path, ".git")):
            return True, "OTHER_GIT_REPO_FORBIDDEN"

        # Bounded shallow traversal of quant-v0.6: only owned subtrees
        if full_path.startswith("/root/workspace/project/quant-v0.6"):
            rel_to_quant = os.path.relpath(full_path, "/root/workspace/project/quant-v0.6")
            first_part = rel_to_quant.split(os.sep)[0]
            if first_part not in ("_artifacts", "_meta", "_venvs", "postp1-gemini-p2-metadata-r1", "."):
                return True, f"UNOWNED_QUANT_WORKTREE_{first_part}"

        # Bounded traversal of /root/workspace/project: never enter other repos, only immediate data dirs
        if full_path.startswith("/root/workspace/project") and not full_path.startswith("/root/workspace/project/quant-v0.6"):
            rel_to_project = os.path.relpath(full_path, "/root/workspace/project")
            first_part = rel_to_project.split(os.sep)[0]
            if os.path.lexists(os.path.join("/root/workspace/project", first_part, ".git")):
                return True, f"OTHER_PROJECT_REPO_{first_part}"
            if first_part not in ("data", "market_data"):
                return True, f"UNAPPROVED_PROJECT_DIR_{first_part}"

        if is_path_protected_holdout(full_path) or is_path_protected_holdout(entry_name):
            self.counters.protected_paths_excluded += 1
            return True, "PROTECTED_EXCLUDED_HOLDOUT"

        return False, ""

    def probe_selected_btc_partitions(
        self, root_dir: str
    ) -> dict[str, PartitionProbeResult]:
        """Probe the 6 selected nonprotected BTC partitions under a candidate root."""
        results: dict[str, PartitionProbeResult] = {}

        for month in SELECTED_SAFE_MONTHS:
            if self.counters.selected_partition_lstat_calls >= self.max_selected_partition_lstat:
                self.stop_reason = f"SELECTED_PARTITION_LSTAT_CAP_{self.max_selected_partition_lstat}"
                results[month] = PartitionProbeResult(
                    month=month,
                    relative_path="",
                    declared_sha256="",
                    physical_exists=False,
                    status=CoverageStatus.UNKNOWN_UNPROBED,
                    reason="BUDGET_CAP_REACHED",
                )
                continue

            manifest_info = DECLARED_BTC_MANIFEST_PARTITIONS.get(month, {})
            rel_path = manifest_info.get("relative_path", "")
            decl_sha = manifest_info.get("declared_sha256", "")

            full_target = os.path.join(root_dir, rel_path)
            self.counters.selected_partition_lstat_calls += 1
            st = self._safe_lstat(full_target)

            if st is not None:
                # File physically exists! Note: file body is NEVER opened
                results[month] = PartitionProbeResult(
                    month=month,
                    relative_path=rel_path,
                    declared_sha256=decl_sha,
                    physical_exists=True,
                    lstat_size_bytes=st.st_size,
                    lstat_mtime=st.st_mtime,
                    status=CoverageStatus.PRESENT_METADATA_ONLY,
                    reason="PHYSICALLY_LOCATED_VIA_LSTAT",
                )
            else:
                results[month] = PartitionProbeResult(
                    month=month,
                    relative_path=rel_path,
                    declared_sha256=decl_sha,
                    physical_exists=False,
                    status=CoverageStatus.MISSING_VERIFIED_SELECTED_PATH,
                    reason="ENOENT_UNDER_CANDIDATE_ROOT",
                )

        return results

    def scan_directory_bounded(
        self, candidate_dir: str, current_depth: int = 0
    ) -> tuple[list[str], list[str]]:
        """Bounded safe directory traversal returning subdirectories and market indicators."""
        subdirs: list[str] = []
        market_indicators: list[str] = []

        self.counters.depth_reached = max(self.counters.depth_reached, current_depth)

        if current_depth >= self.max_depth:
            return subdirs, market_indicators

        if self.budget_exhausted or self.stop_reason is not None:
            return subdirs, market_indicators

        # Safe directory entry listing
        try:
            # Deterministic alphabetical ordering
            entries = sorted(os.listdir(candidate_dir))
        except (PermissionError, FileNotFoundError, NotADirectoryError) as exc:
            if isinstance(exc, PermissionError):
                self.counters.permission_denied_entries += 1
            return subdirs, market_indicators

        for name in entries:
            if self.counters.dir_entries_scanned >= self.max_dir_entries:
                self.stop_reason = f"DIR_ENTRIES_CAP_REACHED_{self.max_dir_entries}"
                self.budget_exhausted = True
                break

            if time.time() - self.start_time > self.max_wall_clock_seconds:
                self.stop_reason = f"WALL_CLOCK_TIMEOUT_{self.max_wall_clock_seconds}s"
                self.budget_exhausted = True
                break

            self.counters.dir_entries_scanned += 1
            full_path = os.path.join(candidate_dir, name)

            # Security and protection checks
            is_blocked, _ = self._is_foreign_or_protected_entry(name, full_path)
            if is_blocked:
                continue

            # Symlink check: NEVER follow symlinks
            try:
                is_link = os.path.islink(full_path)
            except OSError:
                is_link = False

            if is_link:
                self.counters.symlinks_encountered += 1
                # MAX_SYMLINK_FOLLOW is 0, so never descend into symlink
                continue

            st = self._safe_lstat(full_path)
            if st is None:
                continue

            # Check market indicators
            lower_name = name.lower()
            if lower_name in ("1m", "klines", "markpriceklines", "fundingrate", "data.parquet") or lower_name.startswith(("year=", "month=")):
                market_indicators.append(full_path)

            # Descend into directory if within depth bound
            if os.path.isdir(full_path):
                subdirs.append(full_path)
                if current_depth + 1 < self.max_depth and not self.budget_exhausted:
                    child_subdirs, child_indicators = self.scan_directory_bounded(
                        full_path, current_depth + 1
                    )
                    subdirs.extend(child_subdirs)
                    market_indicators.extend(child_indicators)

        return subdirs, market_indicators

    def evaluate_candidate(self, candidate_path: str) -> CandidateEvaluation:
        """Evaluate a single candidate root."""
        # 1. Check forbidden roots
        is_fb, fb_reason = self._is_forbidden_root(candidate_path)
        if is_fb:
            self.counters.forbidden_roots_rejected += 1
            return CandidateEvaluation(
                candidate_root=candidate_path,
                exists=False,
                is_symlink=False,
                is_dir=False,
                ownership_authorized=False,
                rejection_reason=fb_reason,
                certainty=RootCertainty.ROOT_UNKNOWN,
            )

        # 2. Check existence & symlink status
        try:
            is_symlink = os.path.islink(candidate_path)
        except OSError:
            is_symlink = False

        if is_symlink:
            self.counters.symlinks_encountered += 1
            return CandidateEvaluation(
                candidate_root=candidate_path,
                exists=True,
                is_symlink=True,
                is_dir=False,
                ownership_authorized=False,
                rejection_reason="SYMLINK_ROOT_REJECTED",
                certainty=RootCertainty.ROOT_UNKNOWN,
            )

        st = self._safe_lstat(candidate_path)
        if st is None:
            return CandidateEvaluation(
                candidate_root=candidate_path,
                exists=False,
                is_symlink=False,
                is_dir=False,
                ownership_authorized=True,
                rejection_reason="ENOENT_ROOT_DOES_NOT_EXIST",
                certainty=RootCertainty.ROOT_UNKNOWN,
            )

        if not os.path.isdir(candidate_path):
            return CandidateEvaluation(
                candidate_root=candidate_path,
                exists=True,
                is_symlink=False,
                is_dir=False,
                ownership_authorized=True,
                rejection_reason="NOT_A_DIRECTORY",
                certainty=RootCertainty.ROOT_UNKNOWN,
            )

        # 3. Perform bounded traversal
        subdirs, market_indicators = self.scan_directory_bounded(candidate_path, current_depth=0)

        # 4. Probe safe partitions under this root or discovered subtrees
        safe_probes = self.probe_selected_btc_partitions(candidate_path)

        # Determine certainty
        confirmed_count = sum(1 for p in safe_probes.values() if p.physical_exists)
        if confirmed_count == len(SELECTED_SAFE_MONTHS):
            certainty = RootCertainty.ROOT_CONFIRMED_FOR_SELECTED_METADATA
        elif confirmed_count > 0 or len(market_indicators) > 0:
            certainty = RootCertainty.ROOT_CANDIDATE_UNVERIFIED
        else:
            certainty = RootCertainty.ROOT_UNKNOWN

        return CandidateEvaluation(
            candidate_root=candidate_path,
            exists=True,
            is_symlink=False,
            is_dir=True,
            ownership_authorized=True,
            rejection_reason=None,
            subdirectories_found=subdirs,
            market_like_indicators=market_indicators,
            safe_partitions_checked=safe_probes,
            certainty=certainty,
        )

    def run(self) -> ScanExecutionReceipt:
        """Execute one bounded reconnaissance run across candidate roots."""
        self.start_time = time.time()
        start_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.start_time))

        evaluations: list[CandidateEvaluation] = []
        confirmed_root: str | None = None

        for cand in self.candidate_roots:
            if self.budget_exhausted:
                break

            ev = self.evaluate_candidate(cand)
            evaluations.append(ev)

            if ev.certainty == RootCertainty.ROOT_CONFIRMED_FOR_SELECTED_METADATA:
                confirmed_root = cand
                # Early stop on verified root: do not consume remaining budget for its own sake!
                break

        end_time = time.time()
        end_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(end_time))
        self.counters.wall_clock_seconds = round(end_time - self.start_time, 4)

        # Determine terminal verdict
        if confirmed_root is not None:
            verdict = TerminalVerdict.P2_SELECTED_LOCAL_ROOT_CONFIRMED_METADATA_ONLY
            owner_request = None
        elif any(e.certainty == RootCertainty.ROOT_CANDIDATE_UNVERIFIED for e in evaluations):
            verdict = TerminalVerdict.P2_LOCAL_ROOT_CANDIDATE_UNVERIFIED
            owner_request = "Provide verified local root path binding containing partition structure."
        elif self.budget_exhausted:
            verdict = TerminalVerdict.P2_BUDGET_EXHAUSTED_UNCONFIRMED
            owner_request = "Execution budget reached without finding valid root."
        else:
            verdict = TerminalVerdict.P2_LOCAL_ROOT_UNKNOWN_WITH_BOUNDED_NEGATIVE_EVIDENCE
            owner_request = (
                "Please provide one exact local owner data root path binding via "
                "--approved-root (e.g. where 1m/year=YYYY/month=MM/data.parquet reside), "
                "or confirm market files reside on remote storage."
            )

        return ScanExecutionReceipt(
            task_id="V06_POST_P1_GEMINI_LONG_P2_METADATA_ROOT_AND_SOURCE_READINESS_R1",
            start_time_iso=start_iso,
            end_time_iso=end_iso,
            duration_seconds=self.counters.wall_clock_seconds,
            counters=self.counters,
            evaluated_roots=evaluations,
            confirmed_root=confirmed_root,
            terminal_verdict=verdict,
            budget_exhausted=self.budget_exhausted,
            stop_reason=self.stop_reason,
            one_owner_request=owner_request,
        )
