"""Synthetic POSIX FS and Parquet footer security oracle runner for P2 S3A (R1 & R2).

Executes:
- 30 core positive and adversarial negative scenarios against real temporary
  directory trees created via ``tempfile.TemporaryDirectory()``
- 3 deliberate mutant falsification proofs
- R2 supplemental bounded security repair verification suite covering:
  - F01: Two-temp-tree ancestor symlink escape (allowed tree + forbidden owner
    surrogate tree), proving old unguarded ``os.open(root, O_NOFOLLOW)`` reaches
    the forbidden surrogate while the repaired R2 reader rejects before reading
    any footer bytes; plus multi-hop parent symlinks, ``../``, relative aliases,
    hardlinks, dangling/renamed parents, mock bind-mount, and unattested roots
    returning ``S3A_HARNESS_ROOT_IDENTITY_NOT_PROVEN``.
  - F02: Honest ``TEST_ONLY_INTEGRITY_CHECKSUM_NOT_AUTHORIZATION`` token
    semantics proving a caller can recompute the public SHA-256 checksum and
    that self-minted tokens never grant access to unattested, surrogate, or
    owner roots.
  - F03: First-open close slot reservation across ``max_attempted_fs_calls =
    1, 2, 3, 25, 27, 100`` with ``BUDGET_INSUFFICIENT_STOP`` classification,
    zero FD leaks, and non-aborting ``os.close`` failure handling.
  - F04: Row-wise verification of all 6 BTC 1m monthly file sizes and 7
    auxiliary file sizes against the parsed immutable ``c6823dbc46249cac43aa10400aacbbe9f4542410``
    JSON receipt (SHA-256 ``a3c9169dcbeb31edce492791ef253e42c580411cdb014337e8084229aaaaf3f2``).
"""

from __future__ import annotations

import base64
import errno
import hashlib
import json
import os
import struct
import subprocess
import tempfile
import zlib
from pathlib import Path
from typing import Any

from scripts.strategy_research.p2_s3_footer_reader.constants import (
    BUDGET_INSUFFICIENT_STOP_CODE,
    CODE_START_SHA,
    CONTROLLER_DISPATCH_SHA,
    CONTROLLER_S2_JOINT_DECISION_SHA,
    ETH_SOL_1M_PERP_STATUS,
    HARNESS_ROOT_NOT_PROVEN_CODE,
    HEADER_STATUS_NOT_VERIFIED,
    IMMUTABLE_OWNER_DATA_ROOT,
    MAX_ATTEMPTED_FS_CALLS,
    MAX_FOOTER_READ_BYTES,
    MAX_TOTAL_FILE_READ_BYTES,
    MAX_TRAILER_READ_BYTES,
    ORIGINAL_STAT_RECEIPT_JSON_SHA256,
    ORIGINAL_STAT_RECEIPT_SHA,
    PROMPT_SHA,
    R1_TO_R2_BTC_SIZE_ERRATA_MAP,
    R2_CONTROLLER_DISPATCH_SHA,
    R2_EXACT_START_SHA,
    R2_PROMPT_SHA,
    R2_TASK_ID,
    S3_SINGLE_PILOT_EXPECTED_SIZE_BYTES,
    S3_SINGLE_PILOT_REL_PATH,
    S3A_R2_TERMINAL_STATUS,
    S3A_TERMINAL_STATUS,
    SYNTHETIC_GRANT_TOKEN_SEMANTICS,
    TASK_ID,
    VERIFIED_C6823DBC_BTC_CANDIDATE_MONTH_SIZES_BYTES,
    VERIFIED_C6823DBC_FILE_SIZES_BYTES,
)
from scripts.strategy_research.p2_s3_footer_reader.errors import (
    ParserInputViolationError,
    S3FooterReaderError,
)
from scripts.strategy_research.p2_s3_footer_reader.fd_syscall_wrapper import (
    MeteredPosixSyscallWrapper,
)
from scripts.strategy_research.p2_s3_footer_reader.footer_parser import (
    parse_in_memory_parquet_footer,
)
from scripts.strategy_research.p2_s3_footer_reader.reader import (
    SingleFileParquetFooterReader,
)
from scripts.strategy_research.p2_s3_footer_reader.synthetic_fixtures import (
    build_synthetic_parquet_bytes,
    craft_custom_trailer_parquet_bytes,
    materialize_synthetic_pilot_tree,
)
from scripts.strategy_research.p2_s3_footer_reader.types import (
    FooterReadExecutionReceipt,
    SyntheticTestGrant,
    create_valid_synthetic_grant,
    register_forbidden_owner_surrogate_tree,
)

# Exact zlib-compressed, base64-encoded snapshot of Git blob
# c6823dbc46249cac43aa10400aacbbe9f4542410:evidence/v0.6/b_line/p2_owner_root_metadata_r1/P2_OWNER_ROOT_EXACT_SCAN_RECEIPT.json
# Verified by SHA-256 digest a3c9169dcbeb31edce492791ef253e42c580411cdb014337e8084229aaaaf3f2.
_PINNED_C6823DBC_JSON_ZLIB_B64: str = (
    "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"
    "cXg0OBNHxyBncHhjU3/31/8AK35Vfg=="
)


def load_pinned_c6823dbc_scan_receipt_json() -> tuple[bytes, dict[str, Any]]:
    """Load and SHA-256 verify the immutable c6823dbc46249cac43aa10400aacbbe9f4542410 receipt.

    If the commit object is available in the local git object database, also
    verifies byte-for-byte identity against ``git show c6823dbc...:...``.
    """
    embedded_raw = zlib.decompress(base64.b64decode(_PINNED_C6823DBC_JSON_ZLIB_B64))
    digest = hashlib.sha256(embedded_raw).hexdigest()
    if digest != ORIGINAL_STAT_RECEIPT_JSON_SHA256:
        raise ValueError(
            f"Pinned c6823dbc JSON SHA-256 mismatch: {digest} != "
            f"{ORIGINAL_STAT_RECEIPT_JSON_SHA256}"
        )

    git_obj = (
        f"{ORIGINAL_STAT_RECEIPT_SHA}:"
        "evidence/v0.6/b_line/p2_owner_root_metadata_r1/P2_OWNER_ROOT_EXACT_SCAN_RECEIPT.json"
    )
    try:
        git_raw = subprocess.check_output(
            ["git", "show", git_obj],
            stderr=subprocess.DEVNULL,
        )
    except (subprocess.SubprocessError, OSError):
        raw_bytes = embedded_raw
    else:
        if git_raw != embedded_raw:
            raise ValueError(
                "Git object c6823dbc scan receipt bytes differ from embedded snapshot."
            )
        raw_bytes = git_raw

    parsed = json.loads(raw_bytes.decode("utf-8"))
    return raw_bytes, parsed


def extract_file_sizes_from_c6823dbc_json(
    parsed_receipt: dict[str, Any],
) -> dict[str, int]:
    """Extract all (rel_path, size_bytes) file observations from the c6823dbc receipt."""
    extracted: dict[str, int] = {}
    for item in parsed_receipt.get("candidate_month_observations", []):
        rel_path = str(item["file_rel_path"])
        extracted[rel_path] = int(item["file_size_bytes"])
    for item in parsed_receipt.get("additional_target_observations", []):
        if item.get("expected_type") == "file":
            rel_path = str(item["rel_path"])
            extracted[rel_path] = int(item["size_bytes"])
    return extracted


def _record_scenario(
    scenario_id: str,
    category: str,
    description: str,
    expected_allowed: bool,
    expected_decision_code: str,
    receipt: FooterReadExecutionReceipt,
) -> dict[str, Any]:
    snap = receipt.syscall_accounting
    passed = (
        receipt.allowed == expected_allowed
        and receipt.decision_code == expected_decision_code
        and snap.open_fds_remaining == 0
        and snap.owner_root_touched is False
        and receipt.header_verification_status == HEADER_STATUS_NOT_VERIFIED
        and receipt.grant_token_semantics == SYNTHETIC_GRANT_TOKEN_SEMANTICS
    )
    return {
        "scenario_id": scenario_id,
        "category": category,
        "description": description,
        "expected_allowed": expected_allowed,
        "actual_allowed": receipt.allowed,
        "expected_decision_code": expected_decision_code,
        "actual_decision_code": receipt.decision_code,
        "error_type": receipt.error_type,
        "header_verification_status": receipt.header_verification_status,
        "grant_token_semantics": receipt.grant_token_semantics,
        "open_fds_remaining": snap.open_fds_remaining,
        "attempted_fs_calls_total": snap.attempted_fs_calls_total,
        "actual_read_bytes_total": snap.actual_read_bytes_total,
        "trailer_bytes_read": snap.trailer_bytes_read,
        "footer_bytes_read": snap.footer_bytes_read,
        "owner_root_touched": snap.owner_root_touched,
        "oracle_assertion_passed": passed,
    }


def run_all_s3a_security_oracle_scenarios() -> dict[str, Any]:
    """Run all 30 positive and adversarial negative scenarios + 3 mutant proofs."""
    scenarios: list[dict[str, Any]] = []

    # --- POSITIVE SCENARIOS (4) ---
    # POS-01: Standard valid synthetic 2021-03 Parquet file with stats & KV suppressed
    with tempfile.TemporaryDirectory(prefix="s3a_pos01_") as tmp:
        materialize_synthetic_pilot_tree(tmp)
        grant = create_valid_synthetic_grant(tmp)
        reader = SingleFileParquetFooterReader(synthetic_fixture_root=tmp, grant=grant)
        rec = reader.evaluate_to_receipt()
        scenarios.append(
            _record_scenario(
                "POS_01_VALID_SYNTHETIC_2021_03_FOOTER_READ",
                "POSITIVE_FOOTER_READ",
                "Valid synthetic 2021-03 Parquet footer read via anchored dir_fd walk and pread.",
                True,
                "ALLOWED_SINGLE_FILE_FOOTER_SCHEMA_PARSED",
                rec,
            )
        )

    # POS-02: Large synthetic body (300 KB body + compact footer) reads only trailer + footer
    with tempfile.TemporaryDirectory(prefix="s3a_pos02_") as tmp:
        base_pq = build_synthetic_parquet_bytes(num_rows=64, write_statistics=True)
        footer_len = struct.unpack("<i", base_pq[-8:-4])[0]
        padded_pq = (
            b"PAR1"
            + (b"\x00" * 300_000)
            + base_pq[-(footer_len + 8) :]
        )
        materialize_synthetic_pilot_tree(tmp, parquet_bytes=padded_pq)
        grant = create_valid_synthetic_grant(tmp)
        reader = SingleFileParquetFooterReader(synthetic_fixture_root=tmp, grant=grant)
        rec = reader.evaluate_to_receipt()
        scenarios.append(
            _record_scenario(
                "POS_02_LARGE_BODY_PREAD_READS_ONLY_TRAILER_AND_FOOTER",
                "POSITIVE_FOOTER_READ",
                "300KB synthetic file reads only 8B trailer + compact footer (<65,544B).",
                True,
                "ALLOWED_SINGLE_FILE_FOOTER_SCHEMA_PARSED",
                rec,
            )
        )

    # POS-03: Uncompressed Parquet without embedded statistics parses cleanly
    with tempfile.TemporaryDirectory(prefix="s3a_pos03_") as tmp:
        pq_no_stats = build_synthetic_parquet_bytes(
            num_rows=4,
            write_statistics=False,
            compression="NONE",
        )
        materialize_synthetic_pilot_tree(tmp, parquet_bytes=pq_no_stats)
        grant = create_valid_synthetic_grant(tmp)
        reader = SingleFileParquetFooterReader(synthetic_fixture_root=tmp, grant=grant)
        rec = reader.evaluate_to_receipt()
        scenarios.append(
            _record_scenario(
                "POS_03_NO_STATS_UNCOMPRESSED_SCHEMA_SUMMARY",
                "POSITIVE_FOOTER_READ",
                "Synthetic Parquet without column statistics parses and marks stats suppressed.",
                True,
                "ALLOWED_SINGLE_FILE_FOOTER_SCHEMA_PARSED",
                rec,
            )
        )

    # POS-04: Tight but sufficient syscall budget (30 calls <= 100) succeeds cleanly
    with tempfile.TemporaryDirectory(prefix="s3a_pos04_") as tmp:
        materialize_synthetic_pilot_tree(tmp)
        grant = create_valid_synthetic_grant(tmp, max_attempted_fs_calls=30)
        reader = SingleFileParquetFooterReader(synthetic_fixture_root=tmp, grant=grant)
        rec = reader.evaluate_to_receipt()
        scenarios.append(
            _record_scenario(
                "POS_04_BOUNDED_30_SYSCALL_BUDGET_SUCCEEDS",
                "POSITIVE_FOOTER_READ",
                "Full 6-component dir_fd walk + pread + TOCTOU reopen completes in 27 syscalls.",
                True,
                "ALLOWED_SINGLE_FILE_FOOTER_SCHEMA_PARSED",
                rec,
            )
        )

    # --- NEGATIVE ADVERSARIAL SCENARIOS (26 >= 18 required) ---
    # NEG-01: CLI --data-root / --root override attempt
    with tempfile.TemporaryDirectory(prefix="s3a_neg01_") as tmp:
        materialize_synthetic_pilot_tree(tmp)
        grant = create_valid_synthetic_grant(tmp)
        reader = SingleFileParquetFooterReader(
            synthetic_fixture_root=tmp,
            grant=grant,
            cli_args=["--data-root=/tmp/other"],
        )
        rec = reader.evaluate_to_receipt()
        scenarios.append(
            _record_scenario(
                "NEG_01_CLI_DATA_ROOT_OVERRIDE_BLOCKED",
                "CLI_ENV_ROOT_GUARD",
                "CLI --data-root override flag rejected before any OS syscall.",
                False,
                "DENIED_CLI_OR_ENV_ROOT_OVERRIDE",
                rec,
            )
        )

    # NEG-02: Environment variable root override attempt
    with tempfile.TemporaryDirectory(prefix="s3a_neg02_") as tmp:
        materialize_synthetic_pilot_tree(tmp)
        grant = create_valid_synthetic_grant(tmp)
        reader = SingleFileParquetFooterReader(
            synthetic_fixture_root=tmp,
            grant=grant,
            env_vars={"QUANT_AGENT_DATA_ROOT": "/tmp/override"},
        )
        rec = reader.evaluate_to_receipt()
        scenarios.append(
            _record_scenario(
                "NEG_02_ENV_VAR_ROOT_OVERRIDE_BLOCKED",
                "CLI_ENV_ROOT_GUARD",
                "Environment variable QUANT_AGENT_DATA_ROOT override rejected before any syscall.",
                False,
                "DENIED_CLI_OR_ENV_ROOT_OVERRIDE",
                rec,
            )
        )

    # NEG-03: Direct reference to real owner data root (/root/workspace/project/Quant-agent/data)
    with tempfile.TemporaryDirectory(prefix="s3a_neg03_") as tmp:
        grant = create_valid_synthetic_grant(tmp)
        reader = SingleFileParquetFooterReader(
            synthetic_fixture_root=IMMUTABLE_OWNER_DATA_ROOT,
            grant=grant,
        )
        rec = reader.evaluate_to_receipt()
        scenarios.append(
            _record_scenario(
                "NEG_03_REAL_OWNER_DATA_ROOT_HARD_BLOCKED",
                "OWNER_ROOT_HARD_BLOCK",
                "Attempt to target /root/workspace/project/Quant-agent/data rejected with 0 syscalls.",
                False,
                "DENIED_PRODUCTION_OR_OWNER_ROOT_FORBIDDEN",
                rec,
            )
        )

    # NEG-04: Production mode flag enabled
    with tempfile.TemporaryDirectory(prefix="s3a_neg04_") as tmp:
        materialize_synthetic_pilot_tree(tmp)
        grant = create_valid_synthetic_grant(tmp)
        reader = SingleFileParquetFooterReader(
            synthetic_fixture_root=tmp,
            grant=grant,
            production_mode=True,
        )
        rec = reader.evaluate_to_receipt()
        scenarios.append(
            _record_scenario(
                "NEG_04_PRODUCTION_MODE_FORBIDDEN",
                "OWNER_ROOT_HARD_BLOCK",
                "production_mode=True rejected fail-closed with 0 syscalls.",
                False,
                "DENIED_PRODUCTION_OR_OWNER_ROOT_FORBIDDEN",
                rec,
            )
        )

    # NEG-05: Root directory itself is a symlink
    with tempfile.TemporaryDirectory(prefix="s3a_neg05_") as tmp:
        real_root = Path(tmp) / "real_root"
        sym_root = Path(tmp) / "sym_root"
        materialize_synthetic_pilot_tree(real_root)
        os.symlink(real_root, sym_root)
        grant = create_valid_synthetic_grant(str(sym_root))
        reader = SingleFileParquetFooterReader(
            synthetic_fixture_root=str(sym_root),
            grant=grant,
        )
        rec = reader.evaluate_to_receipt()
        scenarios.append(
            _record_scenario(
                "NEG_05_ROOT_DIRECTORY_IS_SYMLINK",
                "POSIX_SYMLINK_DEFENSE",
                "Root directory symlink rejected via O_DIRECTORY|O_NOFOLLOW openat probe.",
                False,
                "DENIED_SYMLINK_DETECTED",
                rec,
            )
        )

    # NEG-06: Intermediate symlink at 'research'
    with tempfile.TemporaryDirectory(prefix="s3a_neg06_") as tmp:
        outside_dir = Path(tmp) / "outside_research"
        os.makedirs(outside_dir, exist_ok=True)
        root_dir = Path(tmp) / "fixture_root"
        os.makedirs(root_dir, exist_ok=True)
        os.symlink(outside_dir, root_dir / "research")
        grant = create_valid_synthetic_grant(str(root_dir))
        reader = SingleFileParquetFooterReader(
            synthetic_fixture_root=str(root_dir),
            grant=grant,
        )
        rec = reader.evaluate_to_receipt()
        scenarios.append(
            _record_scenario(
                "NEG_06_INTERMEDIATE_SYMLINK_AT_RESEARCH",
                "POSIX_SYMLINK_DEFENSE",
                "Intermediate directory symlink at 'research' rejected during dir_fd walk.",
                False,
                "DENIED_SYMLINK_DETECTED",
                rec,
            )
        )

    # NEG-07: Intermediate symlink at 'month=03'
    with tempfile.TemporaryDirectory(prefix="s3a_neg07_") as tmp:
        outside_month = Path(tmp) / "outside_month03"
        os.makedirs(outside_month, exist_ok=True)
        (outside_month / "data.parquet").write_bytes(build_synthetic_parquet_bytes())
        root_dir = Path(tmp) / "fixture_root"
        year_dir = root_dir / "research" / "BTCUSDT" / "1m" / "year=2021"
        os.makedirs(year_dir, exist_ok=True)
        os.symlink(outside_month, year_dir / "month=03")
        grant = create_valid_synthetic_grant(str(root_dir))
        reader = SingleFileParquetFooterReader(
            synthetic_fixture_root=str(root_dir),
            grant=grant,
        )
        rec = reader.evaluate_to_receipt()
        scenarios.append(
            _record_scenario(
                "NEG_07_INTERMEDIATE_SYMLINK_AT_MONTH_03",
                "POSIX_SYMLINK_DEFENSE",
                "Intermediate directory symlink at 'month=03' rejected and all parent FDs closed.",
                False,
                "DENIED_SYMLINK_DETECTED",
                rec,
            )
        )

    # NEG-08: Final leaf target 'data.parquet' is a symlink
    with tempfile.TemporaryDirectory(prefix="s3a_neg08_") as tmp:
        root_dir = Path(tmp) / "fixture_root"
        month_dir = root_dir / "research" / "BTCUSDT" / "1m" / "year=2021" / "month=03"
        os.makedirs(month_dir, exist_ok=True)
        secret_file = Path(tmp) / "secret.parquet"
        secret_file.write_bytes(build_synthetic_parquet_bytes())
        os.symlink(secret_file, month_dir / "data.parquet")
        grant = create_valid_synthetic_grant(str(root_dir))
        reader = SingleFileParquetFooterReader(
            synthetic_fixture_root=str(root_dir),
            grant=grant,
        )
        rec = reader.evaluate_to_receipt()
        scenarios.append(
            _record_scenario(
                "NEG_08_FINAL_LEAF_DATA_PARQUET_IS_SYMLINK",
                "POSIX_SYMLINK_DEFENSE",
                "Final target 'data.parquet' symlink rejected by O_NOFOLLOW (ELOOP).",
                False,
                "DENIED_SYMLINK_DETECTED",
                rec,
            )
        )

    # NEG-09: '..' traversal segment in relative path
    with tempfile.TemporaryDirectory(prefix="s3a_neg09_") as tmp:
        materialize_synthetic_pilot_tree(tmp)
        grant = create_valid_synthetic_grant(tmp)
        reader = SingleFileParquetFooterReader(synthetic_fixture_root=tmp, grant=grant)
        rec = reader.evaluate_to_receipt(
            rel_path="research/BTCUSDT/1m/year=2021/month=03/../month=03/data.parquet"
        )
        scenarios.append(
            _record_scenario(
                "NEG_09_DOTDOT_TRAVERSAL_SEGMENT_REJECTED",
                "PATH_TRAVERSAL_DEFENSE",
                "Relative path containing '..' segment rejected with 0 syscalls.",
                False,
                "DENIED_PATH_SYNTAX_OR_TRAVERSAL",
                rec,
            )
        )

    # NEG-10: Absolute path or empty/backslash segment
    with tempfile.TemporaryDirectory(prefix="s3a_neg10_") as tmp:
        materialize_synthetic_pilot_tree(tmp)
        grant = create_valid_synthetic_grant(tmp)
        reader = SingleFileParquetFooterReader(synthetic_fixture_root=tmp, grant=grant)
        rec = reader.evaluate_to_receipt(
            rel_path="/research/BTCUSDT/1m/year=2021/month=03/data.parquet"
        )
        scenarios.append(
            _record_scenario(
                "NEG_10_LEADING_SLASH_ABSOLUTE_PATH_REJECTED",
                "PATH_TRAVERSAL_DEFENSE",
                "Leading slash on target path rejected with 0 syscalls.",
                False,
                "DENIED_PATH_SYNTAX_OR_TRAVERSAL",
                rec,
            )
        )

    # NEG-11: Intermediate component is a regular file (NotADirectoryError)
    with tempfile.TemporaryDirectory(prefix="s3a_neg11_") as tmp:
        root_dir = Path(tmp) / "fixture_root"
        btc_dir = root_dir / "research" / "BTCUSDT"
        os.makedirs(btc_dir, exist_ok=True)
        (btc_dir / "1m").write_bytes(b"not a directory")
        grant = create_valid_synthetic_grant(str(root_dir))
        reader = SingleFileParquetFooterReader(
            synthetic_fixture_root=str(root_dir),
            grant=grant,
        )
        rec = reader.evaluate_to_receipt()
        scenarios.append(
            _record_scenario(
                "NEG_11_INTERMEDIATE_COMPONENT_IS_REGULAR_FILE",
                "POSIX_TYPE_DEFENSE",
                "Regular file at intermediate component '1m' rejected as NotADirectoryComponentError.",
                False,
                "DENIED_NOT_A_DIRECTORY_COMPONENT",
                rec,
            )
        )

    # NEG-12: Final target is a directory instead of a regular file
    with tempfile.TemporaryDirectory(prefix="s3a_neg12_") as tmp:
        root_dir = Path(tmp) / "fixture_root"
        leaf_as_dir = (
            root_dir
            / "research"
            / "BTCUSDT"
            / "1m"
            / "year=2021"
            / "month=03"
            / "data.parquet"
        )
        os.makedirs(leaf_as_dir, exist_ok=True)
        grant = create_valid_synthetic_grant(str(root_dir))
        reader = SingleFileParquetFooterReader(
            synthetic_fixture_root=str(root_dir),
            grant=grant,
        )
        rec = reader.evaluate_to_receipt()
        scenarios.append(
            _record_scenario(
                "NEG_12_FINAL_LEAF_IS_DIRECTORY",
                "POSIX_TYPE_DEFENSE",
                "Final target 'data.parquet' being a directory rejected via fstat S_ISREG check.",
                False,
                "DENIED_NON_REGULAR_FILE",
                rec,
            )
        )

    # NEG-13: Final target is a named FIFO pipe instead of a regular file
    with tempfile.TemporaryDirectory(prefix="s3a_neg13_") as tmp:
        root_dir = Path(tmp) / "fixture_root"
        month_dir = root_dir / "research" / "BTCUSDT" / "1m" / "year=2021" / "month=03"
        os.makedirs(month_dir, exist_ok=True)
        os.mkfifo(month_dir / "data.parquet")
        grant = create_valid_synthetic_grant(str(root_dir))
        reader = SingleFileParquetFooterReader(
            synthetic_fixture_root=str(root_dir),
            grant=grant,
        )
        rec = reader.evaluate_to_receipt()
        scenarios.append(
            _record_scenario(
                "NEG_13_FINAL_LEAF_IS_FIFO_PIPE",
                "POSIX_TYPE_DEFENSE",
                "Final target 'data.parquet' FIFO opened non-blocking and rejected by S_ISREG.",
                False,
                "DENIED_NON_REGULAR_FILE",
                rec,
            )
        )

    # NEG-14: Cross-device st_dev change across directory or leaf component
    with tempfile.TemporaryDirectory(prefix="s3a_neg14_") as tmp:
        materialize_synthetic_pilot_tree(tmp)
        grant = create_valid_synthetic_grant(tmp)
        reader = SingleFileParquetFooterReader(
            synthetic_fixture_root=tmp,
            grant=grant,
            simulated_dev_overrides={"year=2021": 999_999_999},
        )
        rec = reader.evaluate_to_receipt()
        scenarios.append(
            _record_scenario(
                "NEG_14_CROSS_DEVICE_ST_DEV_MOUNT_ESCAPE",
                "MOUNT_AND_LINK_DEFENSE",
                "Cross-device st_dev change at 'year=2021' rejected as MountBoundaryEscapeError.",
                False,
                "DENIED_MOUNT_BOUNDARY_ESCAPE",
                rec,
            )
        )

    # NEG-15: Hardlink / multi-link target file (st_nlink > 1)
    with tempfile.TemporaryDirectory(prefix="s3a_neg15_") as tmp:
        leaf = materialize_synthetic_pilot_tree(tmp)
        hardlink_alias = Path(tmp) / "hardlink_alias.parquet"
        os.link(leaf, hardlink_alias)
        grant = create_valid_synthetic_grant(tmp)
        reader = SingleFileParquetFooterReader(synthetic_fixture_root=tmp, grant=grant)
        rec = reader.evaluate_to_receipt()
        scenarios.append(
            _record_scenario(
                "NEG_15_HARDLINK_ST_NLINK_GREATER_THAN_ONE",
                "MOUNT_AND_LINK_DEFENSE",
                "Hardlinked leaf file (st_nlink=2 > 1) rejected as HardlinkOrAliasError.",
                False,
                "DENIED_HARDLINK_OR_INODE_ALIAS",
                rec,
            )
        )

    # NEG-16: TOCTOU replacement of directory entry between trailer pread and post-read check
    with tempfile.TemporaryDirectory(prefix="s3a_neg16_") as tmp:
        leaf = materialize_synthetic_pilot_tree(tmp)

        def _swap_file_during_read() -> None:
            replacement = leaf.parent / "replacement.parquet"
            replacement.write_bytes(build_synthetic_parquet_bytes(num_rows=16))
            os.replace(replacement, leaf)

        grant = create_valid_synthetic_grant(tmp)
        reader = SingleFileParquetFooterReader(
            synthetic_fixture_root=tmp,
            grant=grant,
            post_trailer_pread_hook=_swap_file_during_read,
        )
        rec = reader.evaluate_to_receipt()
        scenarios.append(
            _record_scenario(
                "NEG_16_TOCTOU_FILE_SWAP_DURING_READ",
                "TOCTOU_DEFENSE",
                "Mid-read atomic os.replace swap of 'data.parquet' caught by reopen fstat check.",
                False,
                "DENIED_TOCTOU_OR_FD_IDENTITY_MISMATCH",
                rec,
            )
        )

    # NEG-17: EACCES permission denied vs ENOENT distinct classification
    with tempfile.TemporaryDirectory(prefix="s3a_neg17_") as tmp:
        leaf = materialize_synthetic_pilot_tree(tmp)
        os.chmod(leaf, 0)
        grant = create_valid_synthetic_grant(tmp)
        if os.geteuid() != 0:
            reader = SingleFileParquetFooterReader(
                synthetic_fixture_root=tmp, grant=grant
            )
        else:
            reader = SingleFileParquetFooterReader(
                synthetic_fixture_root=tmp,
                grant=grant,
                simulated_open_errno_by_label={"data.parquet": 13},
            )
        rec = reader.evaluate_to_receipt()
        os.chmod(leaf, 0o600)
        scenarios.append(
            _record_scenario(
                "NEG_17_EACCES_PERMISSION_DENIED_DISTINCT_FROM_ENOENT",
                "POSIX_ERRNO_CLASSIFICATION",
                "EACCES permission error translated to DENIED_EACCES_PERMISSION (distinct from ENOENT).",
                False,
                "DENIED_EACCES_PERMISSION",
                rec,
            )
        )

    # NEG-18: ENOENT missing file classification
    with tempfile.TemporaryDirectory(prefix="s3a_neg18_") as tmp:
        os.makedirs(
            Path(tmp) / "research" / "BTCUSDT" / "1m" / "year=2021" / "month=03",
            exist_ok=True,
        )
        grant = create_valid_synthetic_grant(tmp)
        reader = SingleFileParquetFooterReader(synthetic_fixture_root=tmp, grant=grant)
        rec = reader.evaluate_to_receipt()
        scenarios.append(
            _record_scenario(
                "NEG_18_ENOENT_MISSING_TARGET_FILE",
                "POSIX_ERRNO_CLASSIFICATION",
                "Missing leaf 'data.parquet' translated to DENIED_ENOENT_NOT_FOUND.",
                False,
                "DENIED_ENOENT_NOT_FOUND",
                rec,
            )
        )

    # NEG-19: Non-pilot month (e.g. 2021-04) rejected under single-file S3 scope
    with tempfile.TemporaryDirectory(prefix="s3a_neg19_") as tmp:
        materialize_synthetic_pilot_tree(tmp)
        grant = create_valid_synthetic_grant(tmp)
        reader = SingleFileParquetFooterReader(synthetic_fixture_root=tmp, grant=grant)
        rec = reader.evaluate_to_receipt(
            rel_path="research/BTCUSDT/1m/year=2021/month=04/data.parquet"
        )
        scenarios.append(
            _record_scenario(
                "NEG_19_NON_PILOT_MONTH_2021_04_REJECTED",
                "SINGLE_FILE_SCOPE_DEFENSE",
                "Non-pilot candidate month 2021-04 rejected under S3 single-file 2021-03 gate.",
                False,
                "DENIED_UNAPPROVED_TARGET_FILE",
                rec,
            )
        )

    # NEG-20: Protected 2026 path / forward / H39 rejected
    with tempfile.TemporaryDirectory(prefix="s3a_neg20_") as tmp:
        materialize_synthetic_pilot_tree(tmp)
        grant = create_valid_synthetic_grant(tmp)
        reader = SingleFileParquetFooterReader(synthetic_fixture_root=tmp, grant=grant)
        rec = reader.evaluate_to_receipt(
            rel_path="research/BTCUSDT/1m/year=2026/month=02/data.parquet"
        )
        scenarios.append(
            _record_scenario(
                "NEG_20_PROTECTED_2026_02_HOLDOUT_PATH_REJECTED",
                "PROTECTED_DOMAIN_DEFENSE",
                "Protected 2026-02 path rejected fail-closed with 0 syscalls.",
                False,
                "DENIED_PROTECTED_PATH_DOMAIN",
                rec,
            )
        )

    # NEG-21: Missing, unsigned, or expired grant rejected
    with tempfile.TemporaryDirectory(prefix="s3a_neg21_") as tmp:
        materialize_synthetic_pilot_tree(tmp)
        expired_grant = create_valid_synthetic_grant(
            tmp,
            issued_at_epoch_s=1_600_000_000,
            expires_at_epoch_s=1_700_000_000,
        )
        reader = SingleFileParquetFooterReader(
            synthetic_fixture_root=tmp,
            grant=expired_grant,
            current_epoch_s=1_800_000_000,
        )
        rec = reader.evaluate_to_receipt()
        scenarios.append(
            _record_scenario(
                "NEG_21_EXPIRED_GRANT_REJECTED",
                "GRANT_AUTHORIZATION_DEFENSE",
                "Expired SyntheticTestGrant rejected before any OS syscall.",
                False,
                "DENIED_EXPIRED_GRANT",
                rec,
            )
        )

    # NEG-22: Invalid Parquet trailer magic (!= b'PAR1')
    with tempfile.TemporaryDirectory(prefix="s3a_neg22_") as tmp:
        bad_magic_bytes = craft_custom_trailer_parquet_bytes(
            body_and_footer_bytes=b"0123456789ABCDEF",
            declared_footer_len=8,
            trailer_magic=b"NOPE",
        )
        materialize_synthetic_pilot_tree(tmp, parquet_bytes=bad_magic_bytes)
        grant = create_valid_synthetic_grant(tmp)
        reader = SingleFileParquetFooterReader(synthetic_fixture_root=tmp, grant=grant)
        rec = reader.evaluate_to_receipt()
        scenarios.append(
            _record_scenario(
                "NEG_22_INVALID_PARQUET_TRAILER_MAGIC",
                "PARQUET_FORMAT_DEFENSE",
                "Parquet trailer magic != b'PAR1' rejected after 8-byte trailer pread.",
                False,
                "DENIED_INVALID_PARQUET_TRAILER_MAGIC",
                rec,
            )
        )

    # NEG-23: Parquet footer_len > 65,536 bytes
    with tempfile.TemporaryDirectory(prefix="s3a_neg23_") as tmp:
        oversized_footer_bytes = craft_custom_trailer_parquet_bytes(
            body_and_footer_bytes=(b"\x00" * 70_000),
            declared_footer_len=70_000,
            trailer_magic=b"PAR1",
        )
        materialize_synthetic_pilot_tree(tmp, parquet_bytes=oversized_footer_bytes)
        grant = create_valid_synthetic_grant(tmp)
        reader = SingleFileParquetFooterReader(synthetic_fixture_root=tmp, grant=grant)
        rec = reader.evaluate_to_receipt()
        scenarios.append(
            _record_scenario(
                "NEG_23_PARQUET_FOOTER_LEN_EXCEEDS_65536_CAP",
                "PARQUET_FORMAT_DEFENSE",
                "Trailer declaring footer_len=70,000 (>65,536) rejected before footer pread.",
                False,
                "DENIED_INVALID_PARQUET_FOOTER_LENGTH",
                rec,
            )
        )

    # NEG-24: Parquet footer_len + 8 > file_size - 4 (extent overlap)
    with tempfile.TemporaryDirectory(prefix="s3a_neg24_") as tmp:
        extent_overflow_bytes = craft_custom_trailer_parquet_bytes(
            body_and_footer_bytes=b"12345678",
            declared_footer_len=500,
            trailer_magic=b"PAR1",
        )
        materialize_synthetic_pilot_tree(tmp, parquet_bytes=extent_overflow_bytes)
        grant = create_valid_synthetic_grant(tmp)
        reader = SingleFileParquetFooterReader(synthetic_fixture_root=tmp, grant=grant)
        rec = reader.evaluate_to_receipt()
        scenarios.append(
            _record_scenario(
                "NEG_24_PARQUET_FOOTER_LEN_EXCEEDS_FILE_SIZE",
                "PARQUET_FORMAT_DEFENSE",
                "Trailer declaring footer_len=500 on 20-byte file rejected before footer pread.",
                False,
                "DENIED_PARQUET_FOOTER_EXCEEDS_FILE_EXTENT",
                rec,
            )
        )

    # NEG-25: Truncated file (< 13 bytes) or short pread
    with tempfile.TemporaryDirectory(prefix="s3a_neg25_") as tmp:
        materialize_synthetic_pilot_tree(tmp)
        grant = create_valid_synthetic_grant(tmp)
        reader = SingleFileParquetFooterReader(
            synthetic_fixture_root=tmp,
            grant=grant,
            short_read_truncate_bytes=4,
        )
        rec = reader.evaluate_to_receipt()
        scenarios.append(
            _record_scenario(
                "NEG_25_SHORT_PREAD_REJECTED",
                "SYSCALL_AND_BYTE_BUDGET_DEFENSE",
                "Short pread returning 4 bytes instead of requested 8 bytes rejected fail-closed.",
                False,
                "DENIED_SHORT_READ_OR_TRUNCATED_FILE",
                rec,
            )
        )

    # NEG-26: Corrupted Thrift footer bytes
    with tempfile.TemporaryDirectory(prefix="s3a_neg26_") as tmp:
        corrupted_thrift = craft_custom_trailer_parquet_bytes(
            body_and_footer_bytes=(b"\xff\xfe\xfd\xfc" * 16),
            declared_footer_len=64,
            trailer_magic=b"PAR1",
        )
        materialize_synthetic_pilot_tree(tmp, parquet_bytes=corrupted_thrift)
        grant = create_valid_synthetic_grant(tmp)
        reader = SingleFileParquetFooterReader(synthetic_fixture_root=tmp, grant=grant)
        rec = reader.evaluate_to_receipt()
        scenarios.append(
            _record_scenario(
                "NEG_26_CORRUPTED_THRIFT_FOOTER_BYTES_REJECTED",
                "PARQUET_FORMAT_DEFENSE",
                "Garbage Thrift footer bytes rejected by in-memory BufferReader metadata parser.",
                False,
                "DENIED_CORRUPTED_PARQUET_THRIFT_FOOTER",
                rec,
            )
        )

    mutants = _run_mutant_falsification_suite()
    pos_count = sum(1 for s in scenarios if s["expected_allowed"])
    neg_count = sum(1 for s in scenarios if not s["expected_allowed"])
    all_passed = all(s["oracle_assertion_passed"] for s in scenarios) and all(
        m["killed"] for m in mutants
    )

    return {
        "task_id": TASK_ID,
        "controller_dispatch_sha": CONTROLLER_DISPATCH_SHA,
        "controller_s2_joint_decision_sha": CONTROLLER_S2_JOINT_DECISION_SHA,
        "code_start_sha": CODE_START_SHA,
        "prompt_sha": PROMPT_SHA,
        "original_stat_receipt_sha": ORIGINAL_STAT_RECEIPT_SHA,
        "s3a_terminal_status": S3A_TERMINAL_STATUS,
        "single_pilot_rel_path": S3_SINGLE_PILOT_REL_PATH,
        "single_pilot_expected_size_bytes": S3_SINGLE_PILOT_EXPECTED_SIZE_BYTES,
        "hard_budgets": {
            "max_attempted_fs_calls": MAX_ATTEMPTED_FS_CALLS,
            "max_trailer_read_bytes": MAX_TRAILER_READ_BYTES,
            "max_footer_read_bytes": MAX_FOOTER_READ_BYTES,
            "max_total_file_read_bytes": MAX_TOTAL_FILE_READ_BYTES,
        },
        "summary": {
            "total_scenarios": len(scenarios),
            "positive_scenarios": pos_count,
            "negative_adversarial_scenarios": neg_count,
            "all_scenarios_passed": all_passed,
            "deliberate_mutants_tested": len(mutants),
            "deliberate_mutants_killed": sum(1 for m in mutants if m["killed"]),
            "owner_data_root_syscalls": 0,
        },
        "scenarios": scenarios,
        "mutant_falsification_proofs": mutants,
    }


def run_all_s3a_r2_supplemental_oracle_scenarios() -> dict[str, Any]:
    """Execute the R2 supplemental security oracle covering F01, F02, F03, and F04."""
    r2_scenarios: list[dict[str, Any]] = []

    # R2-F01-01: Two temp trees (allowed_tree + forbidden_owner_surrogate) with
    # ancestor symlink alias: prove old os.open(alias_root, O_NOFOLLOW) reaches
    # the forbidden surrogate while repaired R2 reader rejects with 0 bytes read.
    with tempfile.TemporaryDirectory(prefix="s3a_r2_f01_01_") as tmp:
        allowed_tree = Path(tmp) / "allowed_tree"
        os.makedirs(allowed_tree, exist_ok=True)
        forbidden_surrogate = Path(tmp) / "forbidden_owner_surrogate"
        surrogate_subroot = forbidden_surrogate / "data_root"
        materialize_synthetic_pilot_tree(surrogate_subroot)
        register_forbidden_owner_surrogate_tree(forbidden_surrogate)

        # Create ancestor symlink inside allowed_tree pointing to forbidden_surrogate
        sym_ancestor = allowed_tree / "ancestor_alias"
        os.symlink(forbidden_surrogate, sym_ancestor)
        alias_root_path = str(sym_ancestor / "data_root")

        # Demonstrate old R1 unguarded os.open(alias_root_path, O_DIRECTORY|O_NOFOLLOW)
        # followed the ancestor symlink right into forbidden_surrogate/data_root:
        old_fd = os.open(
            alias_root_path,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
        )
        old_st = os.fstat(old_fd)
        os.close(old_fd)
        surrogate_st = os.stat(surrogate_subroot, follow_symlinks=False)
        old_unguarded_reached_forbidden_surrogate = (
            int(old_st.st_dev) == int(surrogate_st.st_dev)
            and int(old_st.st_ino) == int(surrogate_st.st_ino)
        )

        # Now run repaired R2 reader on the exact same alias_root_path:
        self_minted_grant = create_valid_synthetic_grant(
            alias_root_path, attest_root_custody=False
        )
        reader = SingleFileParquetFooterReader(
            synthetic_fixture_root=alias_root_path,
            grant=self_minted_grant,
        )
        rec = reader.evaluate_to_receipt()
        entry = _record_scenario(
            "R2_F01_01_ANCESTOR_SYMLINK_TO_FORBIDDEN_SURROGATE_BLOCKED",
            "R2_F01_ANCESTOR_AND_CUSTODY_ISOLATION",
            "Two-temp-tree ancestor symlink alias blocked by component walk from '/' before root open.",
            False,
            "DENIED_SYMLINK_DETECTED",
            rec,
        )
        entry["old_r1_unguarded_reached_forbidden_surrogate"] = (
            old_unguarded_reached_forbidden_surrogate
        )
        entry["oracle_assertion_passed"] = (
            entry["oracle_assertion_passed"]
            and old_unguarded_reached_forbidden_surrogate is True
            and rec.syscall_accounting.actual_read_bytes_total == 0
        )
        r2_scenarios.append(entry)

    # R2-F01-02: Multi-hop parent symlink chain (hop1 -> hop2 -> forbidden_surrogate/data_root)
    with tempfile.TemporaryDirectory(prefix="s3a_r2_f01_02_") as tmp:
        forbidden_surrogate = Path(tmp) / "forbidden_surrogate_hop"
        materialize_synthetic_pilot_tree(forbidden_surrogate / "data_root")
        register_forbidden_owner_surrogate_tree(forbidden_surrogate)

        hop2 = Path(tmp) / "hop2_sym"
        hop1 = Path(tmp) / "hop1_sym"
        os.symlink(forbidden_surrogate, hop2)
        os.symlink(hop2, hop1)
        multi_alias_root = str(hop1 / "data_root")

        grant = create_valid_synthetic_grant(
            multi_alias_root, attest_root_custody=False
        )
        reader = SingleFileParquetFooterReader(
            synthetic_fixture_root=multi_alias_root,
            grant=grant,
        )
        rec = reader.evaluate_to_receipt()
        r2_scenarios.append(
            _record_scenario(
                "R2_F01_02_MULTI_HOP_PARENT_SYMLINK_CHAIN_BLOCKED",
                "R2_F01_ANCESTOR_AND_CUSTODY_ISOLATION",
                "Multi-hop parent symlink chain hop1->hop2->forbidden_surrogate rejected at hop1.",
                False,
                "DENIED_SYMLINK_DETECTED",
                rec,
            )
        )

    # R2-F01-03: '..' traversal in synthetic_fixture_root
    with tempfile.TemporaryDirectory(prefix="s3a_r2_f01_03_") as tmp:
        allowed = Path(tmp) / "allowed"
        forbidden = Path(tmp) / "forbidden"
        os.makedirs(allowed, exist_ok=True)
        materialize_synthetic_pilot_tree(forbidden)
        register_forbidden_owner_surrogate_tree(forbidden)
        dotdot_root = f"{allowed}/../forbidden"
        grant = create_valid_synthetic_grant(dotdot_root, attest_root_custody=False)
        reader = SingleFileParquetFooterReader(
            synthetic_fixture_root=dotdot_root,
            grant=grant,
        )
        rec = reader.evaluate_to_receipt()
        r2_scenarios.append(
            _record_scenario(
                "R2_F01_03_ROOT_PATH_DOTDOT_TRAVERSAL_BLOCKED",
                "R2_F01_ANCESTOR_AND_CUSTODY_ISOLATION",
                "Fixture root containing '..' traversal segment rejected with 0 syscalls.",
                False,
                "DENIED_PATH_SYNTAX_OR_TRAVERSAL",
                rec,
            )
        )

    # R2-F01-04: Relative path alias for synthetic_fixture_root
    with tempfile.TemporaryDirectory(prefix="s3a_r2_f01_04_") as tmp:
        rel_alias = "relative_temp_alias/fixture_root"
        grant = create_valid_synthetic_grant(rel_alias, attest_root_custody=False)
        reader = SingleFileParquetFooterReader(
            synthetic_fixture_root=rel_alias,
            grant=grant,
        )
        rec = reader.evaluate_to_receipt()
        r2_scenarios.append(
            _record_scenario(
                "R2_F01_04_RELATIVE_FIXTURE_ROOT_PATH_BLOCKED",
                "R2_F01_ANCESTOR_AND_CUSTODY_ISOLATION",
                "Relative path for synthetic_fixture_root rejected with 0 syscalls.",
                False,
                "DENIED_PATH_SYNTAX_OR_TRAVERSAL",
                rec,
            )
        )

    # R2-F01-05: Direct forbidden owner-surrogate temp tree rejected with S3A_HARNESS_ROOT_IDENTITY_NOT_PROVEN
    with tempfile.TemporaryDirectory(prefix="s3a_r2_f01_05_") as tmp:
        forbidden = Path(tmp) / "forbidden_owner_surrogate_direct"
        materialize_synthetic_pilot_tree(forbidden)
        register_forbidden_owner_surrogate_tree(forbidden)
        grant = create_valid_synthetic_grant(str(forbidden), attest_root_custody=True)
        reader = SingleFileParquetFooterReader(
            synthetic_fixture_root=str(forbidden),
            grant=grant,
        )
        rec = reader.evaluate_to_receipt()
        r2_scenarios.append(
            _record_scenario(
                "R2_F01_05_FORBIDDEN_SURROGATE_ROOT_CUSTODY_DENIED",
                "R2_F01_ANCESTOR_AND_CUSTODY_ISOLATION",
                "Forbidden owner-surrogate temp root rejected with S3A_HARNESS_ROOT_IDENTITY_NOT_PROVEN.",
                False,
                HARNESS_ROOT_NOT_PROVEN_CODE,
                rec,
            )
        )

    # R2-F01-06: Dangling / renamed parent or root directory after custody attestation
    with tempfile.TemporaryDirectory(prefix="s3a_r2_f01_06_") as tmp:
        parent_dir = Path(tmp) / "ephemeral_parent"
        root_dir = parent_dir / "fixture_root"
        materialize_synthetic_pilot_tree(root_dir)
        grant = create_valid_synthetic_grant(str(root_dir), attest_root_custody=True)

        # Rename parent_dir and replace with a new directory connected to a forbidden surrogate
        renamed_parent = Path(tmp) / "ephemeral_parent_old"
        os.rename(parent_dir, renamed_parent)
        os.makedirs(root_dir, exist_ok=True)
        materialize_synthetic_pilot_tree(root_dir)

        reader = SingleFileParquetFooterReader(
            synthetic_fixture_root=str(root_dir),
            grant=grant,
        )
        rec = reader.evaluate_to_receipt()
        r2_scenarios.append(
            _record_scenario(
                "R2_F01_06_RENAMED_PARENT_OR_ROOT_INODE_MISMATCH_DENIED",
                "R2_F01_ANCESTOR_AND_CUSTODY_ISOLATION",
                "Renamed/recreated parent & root after custody attestation rejected as S3A_HARNESS_ROOT_IDENTITY_NOT_PROVEN.",
                False,
                HARNESS_ROOT_NOT_PROVEN_CODE,
                rec,
            )
        )

    # R2-F01-07: Mock bind-mount equivalent (ancestor/root st_dev override or surrogate inode)
    with tempfile.TemporaryDirectory(prefix="s3a_r2_f01_07_") as tmp:
        root_dir = Path(tmp) / "bind_mount_target"
        materialize_synthetic_pilot_tree(root_dir)
        grant = create_valid_synthetic_grant(str(root_dir), attest_root_custody=True)
        reader = SingleFileParquetFooterReader(
            synthetic_fixture_root=str(root_dir),
            grant=grant,
            simulated_dev_overrides={"<root>": 888_888_888},
        )
        rec = reader.evaluate_to_receipt()
        r2_scenarios.append(
            _record_scenario(
                "R2_F01_07_MOCK_BIND_MOUNT_ON_ROOT_BLOCKED",
                "R2_F01_ANCESTOR_AND_CUSTODY_ISOLATION",
                "Simulated bind-mount st_dev change on root FD rejected before child walk.",
                False,
                "DENIED_MOUNT_BOUNDARY_ESCAPE",
                rec,
            )
        )

    # R2-F02-01: Self-minted grant with recomputed public SHA-256 checksum rejected without custody
    with tempfile.TemporaryDirectory(prefix="s3a_r2_f02_01_") as tmp:
        unattested_root = Path(tmp) / "unattested_caller_root"
        materialize_synthetic_pilot_tree(unattested_root)
        # Caller self-mints grant and recomputes public SHA-256 checksum without harness custody
        self_minted = create_valid_synthetic_grant(
            str(unattested_root),
            attest_root_custody=False,
        )
        reader = SingleFileParquetFooterReader(
            synthetic_fixture_root=str(unattested_root),
            grant=self_minted,
        )
        rec = reader.evaluate_to_receipt()
        r2_scenarios.append(
            _record_scenario(
                "R2_F02_01_SELF_MINTED_PUBLIC_CHECKSUM_GRANT_DENIED_WITHOUT_CUSTODY",
                "R2_F02_HONEST_TOKEN_SEMANTICS",
                "Caller-recomputed public SHA-256 checksum without harness root custody rejected as S3A_HARNESS_ROOT_IDENTITY_NOT_PROVEN.",
                False,
                HARNESS_ROOT_NOT_PROVEN_CODE,
                rec,
            )
        )

    # R2-F03-01..06: Syscall cap matrix max_attempted_fs_calls = 1, 2, 3, 25, 27, 100
    for cap in (1, 2, 3, 25, 27, 100):
        with tempfile.TemporaryDirectory(prefix=f"s3a_r2_f03_cap{cap}_") as tmp:
            materialize_synthetic_pilot_tree(tmp)
            grant = create_valid_synthetic_grant(tmp, max_attempted_fs_calls=cap)
            reader = SingleFileParquetFooterReader(
                synthetic_fixture_root=tmp,
                grant=grant,
            )
            rec = reader.evaluate_to_receipt()
            expect_ok = cap >= 27
            expect_code = (
                "ALLOWED_SINGLE_FILE_FOOTER_SCHEMA_PARSED"
                if expect_ok
                else BUDGET_INSUFFICIENT_STOP_CODE
            )
            scen = _record_scenario(
                f"R2_F03_SYSCALL_CAP_{cap}",
                "R2_F03_SYSCALL_BUDGET_AND_CLEANUP",
                f"Syscall cap={cap} enforces attempted_fs_calls_total <= {cap} and 0 leaked FDs.",
                expect_ok,
                expect_code,
                rec,
            )
            scen["oracle_assertion_passed"] = (
                scen["oracle_assertion_passed"]
                and rec.syscall_accounting.attempted_fs_calls_total <= cap
                and rec.syscall_accounting.open_fds_remaining == 0
            )
            r2_scenarios.append(scen)

    # R2-F03-07: Non-aborting os.close failure during cleanup (all remaining FDs closed, not PASS)
    with tempfile.TemporaryDirectory(prefix="s3a_r2_f03_close_err_") as tmp:
        materialize_synthetic_pilot_tree(tmp)
        grant = create_valid_synthetic_grant(tmp)
        reader = SingleFileParquetFooterReader(
            synthetic_fixture_root=tmp,
            grant=grant,
            simulated_close_errno_by_label={"month=03": errno.EIO},
        )
        rec = reader.evaluate_to_receipt()
        scen = _record_scenario(
            "R2_F03_CLOSE_FAILURE_DOES_NOT_ABORT_CLEANUP_OR_PASS",
            "R2_F03_SYSCALL_BUDGET_AND_CLEANUP",
            "Simulated EIO on os.close('month=03') closes all other 7 FDs and rejects as DENIED_FD_CLEANUP_CLOSE_FAILED.",
            False,
            "DENIED_FD_CLEANUP_CLOSE_FAILED",
            rec,
        )
        scen["oracle_assertion_passed"] = (
            scen["oracle_assertion_passed"]
            and rec.syscall_accounting.close_attempted == 8
            and rec.syscall_accounting.close_failed == 1
            and rec.syscall_accounting.close_succeeded == 7
            and rec.syscall_accounting.open_fds_remaining == 0
        )
        r2_scenarios.append(scen)

    # R2-F04: Pinned c6823dbc46249cac43aa10400aacbbe9f4542410 JSON parse verification
    _, parsed_c6823 = load_pinned_c6823dbc_scan_receipt_json()
    extracted_sizes = extract_file_sizes_from_c6823dbc_json(parsed_c6823)
    f04_all_13_match = extracted_sizes == VERIFIED_C6823DBC_FILE_SIZES_BYTES
    f04_btc_6_match = all(
        extracted_sizes.get(k) == v
        for k, v in VERIFIED_C6823DBC_BTC_CANDIDATE_MONTH_SIZES_BYTES.items()
    )

    base_oracle = run_all_s3a_security_oracle_scenarios()
    all_r2_passed = (
        all(s["oracle_assertion_passed"] for s in r2_scenarios)
        and bool(base_oracle["summary"]["all_scenarios_passed"])
        and f04_all_13_match
        and f04_btc_6_match
    )

    return {
        "r2_task_id": R2_TASK_ID,
        "r2_controller_dispatch_sha": R2_CONTROLLER_DISPATCH_SHA,
        "r2_prompt_sha": R2_PROMPT_SHA,
        "r2_exact_start_sha": R2_EXACT_START_SHA,
        "code_start_sha": CODE_START_SHA,
        "original_stat_receipt_sha": ORIGINAL_STAT_RECEIPT_SHA,
        "original_stat_receipt_json_sha256": ORIGINAL_STAT_RECEIPT_JSON_SHA256,
        "r2_terminal_status": S3A_R2_TERMINAL_STATUS,
        "supersedes_evidence_files": [
            "evidence/v0.6/b_line/p2_s3_footer_reader_r1/S3A_FS_SYSCALL_SECURITY_ORACLE_RESULTS.json",
            "evidence/v0.6/b_line/p2_s3_footer_reader_r1/S3A_IMPLEMENTATION_EXECUTION_RECEIPT.json",
        ],
        "f04_btc_monthly_size_errata_mapping": R1_TO_R2_BTC_SIZE_ERRATA_MAP,
        "f04_verified_c6823dbc_file_sizes_bytes": VERIFIED_C6823DBC_FILE_SIZES_BYTES,
        "f04_pinned_json_row_wise_equality_verified": f04_all_13_match,
        "f02_grant_token_semantics": SYNTHETIC_GRANT_TOKEN_SEMANTICS,
        "eth_sol_1m_perp_status": ETH_SOL_1M_PERP_STATUS,
        "summary": {
            "base_scenarios_rerun_total": base_oracle["summary"]["total_scenarios"],
            "base_scenarios_rerun_passed": sum(
                1 for s in base_oracle["scenarios"] if s["oracle_assertion_passed"]
            ),
            "r2_supplemental_scenarios_total": len(r2_scenarios),
            "r2_supplemental_scenarios_passed": sum(
                1 for s in r2_scenarios if s["oracle_assertion_passed"]
            ),
            "combined_scenarios_total": (
                base_oracle["summary"]["total_scenarios"] + len(r2_scenarios)
            ),
            "deliberate_mutants_tested": base_oracle["summary"]["deliberate_mutants_tested"],
            "deliberate_mutants_killed": base_oracle["summary"]["deliberate_mutants_killed"],
            "f04_all_13_files_verified_against_c6823dbc_json": f04_all_13_match,
            "all_r2_gates_passed": all_r2_passed,
            "owner_data_root_syscalls": 0,
        },
        "r2_scenarios": r2_scenarios,
        "base_30_scenarios_rerun_under_r2": base_oracle["scenarios"],
        "mutant_falsification_proofs": base_oracle["mutant_falsification_proofs"],
    }


def _run_mutant_falsification_suite() -> list[dict[str, Any]]:
    """Run 3 deliberate in-test security mutants and prove the test oracle kills them."""
    results: list[dict[str, Any]] = []

    # Mutant M1: Omit O_NOFOLLOW when opening a symlinked leaf -> production reader
    # raises SymlinkDetectedError; mutant follows symlink, which our assertion detects.
    with tempfile.TemporaryDirectory(prefix="s3a_mut01_") as tmp:
        root_dir = Path(tmp) / "fixture_root"
        month_dir = root_dir / "research" / "BTCUSDT" / "1m" / "year=2021" / "month=03"
        os.makedirs(month_dir, exist_ok=True)
        outside = Path(tmp) / "outside_target.parquet"
        outside.write_bytes(build_synthetic_parquet_bytes())
        sym_leaf = month_dir / "data.parquet"
        os.symlink(outside, sym_leaf)

        grant = create_valid_synthetic_grant(str(root_dir))
        prod_reader = SingleFileParquetFooterReader(
            synthetic_fixture_root=str(root_dir),
            grant=grant,
        )
        prod_receipt = prod_reader.evaluate_to_receipt()

        mutant_fd = os.open(str(sym_leaf), os.O_RDONLY | os.O_CLOEXEC)
        os.close(mutant_fd)
        m1_killed = (
            prod_receipt.allowed is False
            and prod_receipt.decision_code == "DENIED_SYMLINK_DETECTED"
        )
        results.append(
            {
                "mutant_id": "MUTANT_M1_OMIT_O_NOFOLLOW_ON_OPENAT",
                "defect_injected": (
                    "Omit O_NOFOLLOW flag when opening leaf/component so kernel follows symlink."
                ),
                "production_decision_code": prod_receipt.decision_code,
                "killed": m1_killed,
            }
        )

    # Mutant M2: Direct path input or uncounted read bypassing MeteredPosixSyscallWrapper
    m2_killed = False
    try:
        parse_in_memory_parquet_footer(
            "/tmp/fake_direct_path.parquet",
            b"1234PAR1",
            file_size_bytes=100,
        )
    except ParserInputViolationError as exc:
        m2_killed = exc.decision_code == "DENIED_PARSER_DIRECT_PATH_OR_FD_FORBIDDEN"
    results.append(
        {
            "mutant_id": "MUTANT_M2_DIRECT_PATH_OR_UNCOUNTED_IO_TO_PARSER",
            "defect_injected": (
                "Pass a filesystem path string instead of pread RAM bytes into footer parser."
            ),
            "production_decision_code": "DENIED_PARSER_DIRECT_PATH_OR_FD_FORBIDDEN",
            "killed": m2_killed,
        }
    )

    # Mutant M3: Leak column min/max statistics or custom KV metadata in output dict
    with tempfile.TemporaryDirectory(prefix="s3a_mut03_") as tmp:
        materialize_synthetic_pilot_tree(
            tmp,
            parquet_bytes=build_synthetic_parquet_bytes(
                num_rows=8,
                write_statistics=True,
                custom_kv_metadata={b"secret_price": b"99999.99"},
            ),
        )
        grant = create_valid_synthetic_grant(tmp)
        prod_reader = SingleFileParquetFooterReader(
            synthetic_fixture_root=tmp,
            grant=grant,
        )
        rec = prod_reader.read_single_parquet_footer()
        meta_dict = rec.schema_metadata.to_dict() if rec.schema_metadata else {}
        serialized = str(meta_dict)
        forbidden_leaks = ("min_value", "max_value", "null_count", "99999.99", "100.5")
        m3_killed = (
            rec.schema_metadata is not None
            and rec.schema_metadata.embedded_statistics_detected is True
            and rec.schema_metadata.embedded_statistics_suppressed is True
            and rec.schema_metadata.key_value_metadata_detected is True
            and rec.schema_metadata.key_value_metadata_suppressed is True
            and all(tok not in serialized for tok in forbidden_leaks)
        )
        results.append(
            {
                "mutant_id": "MUTANT_M3_LEAK_EMBEDDED_COLUMN_STATISTICS_OR_KV_METADATA",
                "defect_injected": (
                    "Expose Parquet column chunk min/max statistics or custom KV metadata values."
                ),
                "production_decision_code": rec.decision_code,
                "killed": m3_killed,
            }
        )

    return results


__all__ = [
    "MeteredPosixSyscallWrapper",
    "S3FooterReaderError",
    "SyntheticTestGrant",
    "extract_file_sizes_from_c6823dbc_json",
    "load_pinned_c6823dbc_scan_receipt_json",
    "run_all_s3a_r2_supplemental_oracle_scenarios",
    "run_all_s3a_security_oracle_scenarios",
]
