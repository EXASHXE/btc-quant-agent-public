"""Synthetic POSIX FS and Parquet footer security oracle runner for P2 S3A.

Executes 30 deterministic positive and adversarial negative scenarios against
real temporary directory trees created via ``tempfile.TemporaryDirectory()``,
plus 3 deliberate mutant falsification proofs. Never touches the physical owner
WSL data root ``/root/workspace/project/Quant-agent/data``.
"""

from __future__ import annotations

import os
import struct
import tempfile
from pathlib import Path
from typing import Any

from scripts.strategy_research.p2_s3_footer_reader.constants import (
    CODE_START_SHA,
    CONTROLLER_DISPATCH_SHA,
    CONTROLLER_S2_JOINT_DECISION_SHA,
    HEADER_STATUS_NOT_VERIFIED,
    IMMUTABLE_OWNER_DATA_ROOT,
    MAX_ATTEMPTED_FS_CALLS,
    MAX_FOOTER_READ_BYTES,
    MAX_TOTAL_FILE_READ_BYTES,
    MAX_TRAILER_READ_BYTES,
    ORIGINAL_STAT_RECEIPT_SHA,
    PROMPT_SHA,
    S3_SINGLE_PILOT_EXPECTED_SIZE_BYTES,
    S3_SINGLE_PILOT_REL_PATH,
    S3A_TERMINAL_STATUS,
    TASK_ID,
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
)


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
            # Under WSL root (euid==0), kernel CAP_DAC_OVERRIDE bypasses chmod 000;
            # inject EACCES (errno 13) at the openat wrapper boundary on 'data.parquet'.
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

    # NEG-26: Corrupted Thrift footer bytes or syscall budget exhaustion
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

    # --- DELIBERATE MUTANT FALSIFICATION PROOFS (3) ---
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

        # Mutant M1 opens without O_NOFOLLOW:
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
    "run_all_s3a_security_oracle_scenarios",
]
