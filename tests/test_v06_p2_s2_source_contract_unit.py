"""Unit tests for P2 S2 source contract specification, token gates, and syscall accounting."""

import json

from scripts.strategy_research.p2_s2_source_contract.constants import (
    CODE_START_SHA,
    CONTROLLER_ADMISSION_DESIGN_SHA,
    CONTROLLER_DISPATCH_SHA,
    CONTROLLER_TERMINATION_SHA,
    IMMUTABLE_OWNER_WSL_DATA_ROOT,
    ORIGINAL_STAT_RECEIPT_SHA,
    RECORDED_METADATA_FILE_SIZES,
    SIX_NONPROTECTED_CANDIDATE_PATHS,
    TASK_ID,
    TERMINATED_LOCATOR_COUNTEREXAMPLE_SHA,
)
from scripts.strategy_research.p2_s2_source_contract.errors import (
    BudgetExceededError,
    EACCESAccessDeniedError,
    ENOENTNotFoundError,
    ZeroBytePolicyViolationError,
)
from scripts.strategy_research.p2_s2_source_contract.policy_kernel import (
    SyntheticSourceContractKernel,
)
from scripts.strategy_research.p2_s2_source_contract.source_map import (
    build_source_scope_and_authority_matrix,
)
from scripts.strategy_research.p2_s2_source_contract.syscall_interface import (
    InMemoryFakeFilesystem,
    InstrumentedSyscallHook,
)
from scripts.strategy_research.p2_s2_source_contract.types import (
    AccessLevel,
    AuditReceipt,
    CapabilityToken,
    InstrumentRole,
    PolicyDecision,
    SyscallAccounting,
)


def _setup_synthetic_fs() -> tuple[InMemoryFakeFilesystem, InstrumentedSyscallHook, str]:
    fake_fs = InMemoryFakeFilesystem()
    root = "/synthetic/data"
    fake_fs.add_directory(root)
    fake_fs.add_directory(f"{root}/research")
    fake_fs.add_directory(f"{root}/research/BTCUSDT")
    fake_fs.add_directory(f"{root}/research/BTCUSDT/1m")

    # Add 6 candidate months
    years = ["2021", "2023", "2025"]
    months = ["03", "04"]
    for y in years:
        fake_fs.add_directory(f"{root}/research/BTCUSDT/1m/year={y}")
        for m in months:
            fake_fs.add_directory(f"{root}/research/BTCUSDT/1m/year={y}/month={m}")
            rel_p = f"research/BTCUSDT/1m/year={y}/month={m}/data.parquet"
            size = RECORDED_METADATA_FILE_SIZES[rel_p]
            fake_fs.add_file(f"{root}/{rel_p}", size=size)

    hook = InstrumentedSyscallHook(fake_fs, max_syscalls=100, max_bytes=0)
    return fake_fs, hook, root


def test_01_authorities_and_pinned_constants() -> None:
    """Verify exact SHAs, paths, and immutable roots match prompt and controller dispatch."""
    assert TASK_ID == "V06_P2_S2_GEMINI_LONG_SOURCE_CONTRACT_AND_SYNTHETIC_CAPABILITY_GATE_R1"
    assert CONTROLLER_DISPATCH_SHA == "b176f4361cd97d1d89c3e25173b2c72a6af93ec4"
    assert CODE_START_SHA == "e0ff8c3473de4bfa3e66fe7928d42992a4d38a32"
    assert ORIGINAL_STAT_RECEIPT_SHA == "c6823dbc46249cac43aa10400aacbbe9f4542410"
    assert TERMINATED_LOCATOR_COUNTEREXAMPLE_SHA == "4a1fcc2871708f0e9e3a7c40036ecaab39ba99b8"
    assert CONTROLLER_TERMINATION_SHA == "ca0b6ea62613e6981b6f818f37f45be8c1d74901"
    assert CONTROLLER_ADMISSION_DESIGN_SHA == "519b2e9ba2ca847e76ad9c0a7fbafcec5fcda158"
    assert IMMUTABLE_OWNER_WSL_DATA_ROOT == "/root/workspace/project/Quant-agent/data"
    assert len(SIX_NONPROTECTED_CANDIDATE_PATHS) == 6


def test_02_access_level_hierarchy_ordering() -> None:
    """Verify L0 < L1 < L2 < L3 < L4 comparisons and monotonicity."""
    assert AccessLevel.L0_LOCATOR < AccessLevel.L1_METADATA
    assert AccessLevel.L1_METADATA < AccessLevel.L2_SCHEMA
    assert AccessLevel.L2_SCHEMA < AccessLevel.L3_QUALITY_QA
    assert AccessLevel.L3_QUALITY_QA < AccessLevel.L4_MARKET_BODY
    assert AccessLevel.L4_MARKET_BODY >= AccessLevel.L0_LOCATOR


def test_03_capability_token_signature_verification() -> None:
    """Valid signature passes; tampered signature fails is_valid_signature()."""
    token = CapabilityToken(
        token_id="tok_001",
        subject="gemini_p2_s2_test",
        allowed_paths=list(SIX_NONPROTECTED_CANDIDATE_PATHS),
        max_level=AccessLevel.L1_METADATA,
    )
    assert token.is_valid_signature()

    # Tamper with token max_level without updating signature
    tampered_token = CapabilityToken(
        token_id="tok_001",
        subject="gemini_p2_s2_test",
        allowed_paths=list(SIX_NONPROTECTED_CANDIDATE_PATHS),
        max_level=AccessLevel.L4_MARKET_BODY,
        signature_hash=token.signature_hash,  # forged/stale signature
    )
    assert not tampered_token.is_valid_signature()


def test_04_capability_token_expiration() -> None:
    """Expired token rejected with DENIED_CAPABILITY_EXPIRED."""
    _, hook, root = _setup_synthetic_fs()
    kernel = SyntheticSourceContractKernel(fixture_root=root, syscall_hook=hook, is_test_mode=True)

    token = CapabilityToken(
        token_id="tok_expired",
        subject="test",
        allowed_paths=list(SIX_NONPROTECTED_CANDIDATE_PATHS),
        max_level=AccessLevel.L1_METADATA,
        created_at_utc="2026-10-01T00:00:00Z",
        expires_at_utc="2026-10-05T00:00:00Z",
    )
    target = SIX_NONPROTECTED_CANDIDATE_PATHS[0]
    receipt = kernel.evaluate_request(
        target_rel_path=target,
        token=token,
        requested_level=AccessLevel.L1_METADATA,
        current_time_utc="2026-10-10T12:00:00Z",
    )
    assert receipt.decision == PolicyDecision.DENIED_CAPABILITY_EXPIRED
    assert receipt.exception_class == "CapabilityTokenExpiredError"


def test_05_capability_level_escalation_denied() -> None:
    """Token with L1 grant cannot request L2 schema or L4 market body."""
    _, hook, root = _setup_synthetic_fs()
    kernel = SyntheticSourceContractKernel(fixture_root=root, syscall_hook=hook, is_test_mode=True)

    token = CapabilityToken(
        token_id="tok_l1_only",
        subject="test",
        allowed_paths=list(SIX_NONPROTECTED_CANDIDATE_PATHS),
        max_level=AccessLevel.L1_METADATA,
    )
    target = SIX_NONPROTECTED_CANDIDATE_PATHS[0]

    # Attempt L2
    receipt_l2 = kernel.evaluate_request(
        target_rel_path=target,
        token=token,
        requested_level=AccessLevel.L2_SCHEMA,
    )
    assert receipt_l2.decision == PolicyDecision.DENIED_UNAUTHORIZED_LEVEL
    assert receipt_l2.exception_class == "CapabilityLevelEscalationError"

    # Attempt L4
    receipt_l4 = kernel.evaluate_request(
        target_rel_path=target,
        token=token,
        requested_level=AccessLevel.L4_MARKET_BODY,
    )
    assert receipt_l4.decision == PolicyDecision.DENIED_UNAUTHORIZED_LEVEL
    assert receipt_l4.exception_class == "CapabilityLevelEscalationError"


def test_06_capability_path_escalation_denied() -> None:
    """Token scoped exclusively for month=03 cannot access month=04."""
    _, hook, root = _setup_synthetic_fs()
    kernel = SyntheticSourceContractKernel(fixture_root=root, syscall_hook=hook, is_test_mode=True)

    allowed_path = "research/BTCUSDT/1m/year=2021/month=03/data.parquet"
    unauthorized_path = "research/BTCUSDT/1m/year=2021/month=04/data.parquet"

    token = CapabilityToken(
        token_id="tok_month03_only",
        subject="test",
        allowed_paths=[allowed_path],
        max_level=AccessLevel.L1_METADATA,
    )

    receipt = kernel.evaluate_request(
        target_rel_path=unauthorized_path,
        token=token,
        requested_level=AccessLevel.L1_METADATA,
    )
    assert receipt.decision == PolicyDecision.DENIED_CAPABILITY_INVALID
    assert "not authorized" in receipt.reason


def test_07_positive_six_candidate_months_permitted_l1() -> None:
    """All 6 non-protected monthly files are permitted under valid L1 token."""
    _, hook, root = _setup_synthetic_fs()
    kernel = SyntheticSourceContractKernel(fixture_root=root, syscall_hook=hook, is_test_mode=True)

    token = CapabilityToken(
        token_id="tok_all_six",
        subject="test",
        allowed_paths=list(SIX_NONPROTECTED_CANDIDATE_PATHS),
        max_level=AccessLevel.L1_METADATA,
    )

    for path in SIX_NONPROTECTED_CANDIDATE_PATHS:
        receipt = kernel.evaluate_request(
            target_rel_path=path,
            token=token,
            requested_level=AccessLevel.L1_METADATA,
            role=InstrumentRole.BTC_PERP_1M_KLINE,
        )
        assert receipt.decision == PolicyDecision.PERMITTED, f"Failed on {path}: {receipt.reason}"
        assert receipt.metadata_size_bytes == RECORDED_METADATA_FILE_SIZES[path]
        assert receipt.exception_class is None


def test_08_non_allowlisted_month_denied() -> None:
    """Candidate month=05 in 2021 is rejected with DENIED_CAPABILITY_INVALID."""
    _, hook, root = _setup_synthetic_fs()
    kernel = SyntheticSourceContractKernel(fixture_root=root, syscall_hook=hook, is_test_mode=True)

    bad_path = "research/BTCUSDT/1m/year=2021/month=05/data.parquet"
    token = CapabilityToken(
        token_id="tok_candidate",
        subject="test",
        allowed_paths=[bad_path],
        max_level=AccessLevel.L1_METADATA,
    )
    receipt = kernel.evaluate_request(
        target_rel_path=bad_path,
        token=token,
        requested_level=AccessLevel.L1_METADATA,
    )
    assert receipt.decision == PolicyDecision.DENIED_CAPABILITY_INVALID
    assert "not in the approved positive allowlist" in receipt.reason


def test_09_syscall_boundary_accounting_precision() -> None:
    """Every single OS-level call increments counters exactly at the boundary."""
    fake_fs = InMemoryFakeFilesystem()
    root = "/test/root"
    fake_fs.add_directory(root)
    fake_fs.add_directory(f"{root}/dir")
    fake_fs.add_file(f"{root}/dir/file.txt", size=100, content=b"A" * 100)

    hook = InstrumentedSyscallHook(fake_fs, max_syscalls=50, max_bytes=200)

    # 1. lstat
    hook.lstat(root)
    assert hook.accounting.lstat_calls == 1
    assert hook.accounting.total_calls == 1

    # 2. open
    fd = hook.open(f"{root}/dir/file.txt", 0)
    assert hook.accounting.open_calls == 1
    assert hook.accounting.total_calls == 2

    # 3. fstat
    hook.fstat(fd)
    assert hook.accounting.fstat_calls == 1
    assert hook.accounting.total_calls == 3

    # 4. read
    chunk = hook.read(fd, 20)
    assert len(chunk) == 20
    assert hook.accounting.read_calls == 1
    assert hook.accounting.bytes_read == 20
    assert hook.accounting.total_calls == 4

    # 5. close
    hook.close(fd)
    assert hook.accounting.close_calls == 1
    assert hook.accounting.total_calls == 5


def test_10_repeated_path_calls_not_cached() -> None:
    """Repeated calls to the same path are individually counted; no unique-path cache."""
    fake_fs = InMemoryFakeFilesystem()
    root = "/test/root"
    fake_fs.add_directory(root)
    fake_fs.add_file(f"{root}/file.txt", size=50)

    hook = InstrumentedSyscallHook(fake_fs, max_syscalls=50, max_bytes=0)

    # Call lstat on the exact same path 5 times
    for _ in range(5):
        hook.lstat(f"{root}/file.txt")

    # Assert exactly 5 calls recorded
    assert hook.accounting.lstat_calls == 5
    assert hook.accounting.total_calls == 5


def test_11_zero_byte_policy_enforcement() -> None:
    """Reading bytes > 0 under max_bytes=0 raises ZeroBytePolicyViolationError."""
    fake_fs = InMemoryFakeFilesystem()
    root = "/test/root"
    fake_fs.add_directory(root)
    fake_fs.add_file(f"{root}/data.bin", size=1024)

    hook = InstrumentedSyscallHook(fake_fs, max_syscalls=20, max_bytes=0)
    fd = hook.open(f"{root}/data.bin", 0)

    try:
        hook.read(fd, 1)
        assert False, "Should have raised ZeroBytePolicyViolationError"
    except ZeroBytePolicyViolationError as exc:
        assert "Zero-byte read policy strictly enforced" in str(exc)


def test_12_syscall_budget_ceiling_enforced() -> None:
    """Exceeding max_syscalls raises BudgetExceededError."""
    fake_fs = InMemoryFakeFilesystem()
    root = "/test/root"
    fake_fs.add_directory(root)

    # Limit to 3 syscalls
    hook = InstrumentedSyscallHook(fake_fs, max_syscalls=3, max_bytes=0)
    hook.lstat(root)
    hook.lstat(root)
    hook.lstat(root)

    try:
        hook.lstat(root)
        assert False, "Should have raised BudgetExceededError"
    except BudgetExceededError as exc:
        assert "Syscall budget ceiling exceeded" in str(exc)


def test_13_eacces_distinct_from_enoent() -> None:
    """PermissionError produces EACCESAccessDeniedError; FileNotFoundError produces ENOENTNotFoundError.

    Verifies the two are strictly distinct in status and exception classes.
    """
    fake_fs = InMemoryFakeFilesystem()
    root = "/test/root"
    fake_fs.add_directory(root)
    fake_fs.add_file(f"{root}/secret.bin", size=10)
    fake_fs.set_permission_denied(f"{root}/secret.bin", True)

    hook = InstrumentedSyscallHook(fake_fs, max_syscalls=20, max_bytes=0)

    # Test EACCES
    try:
        hook.lstat(f"{root}/secret.bin")
        assert False, "Should have raised EACCESAccessDeniedError"
    except EACCESAccessDeniedError as exc:
        assert "EACCES" in str(exc)

    # Test ENOENT
    try:
        hook.lstat(f"{root}/nonexistent.bin")
        assert False, "Should have raised ENOENTNotFoundError"
    except ENOENTNotFoundError as exc:
        assert "ENOENT" in str(exc)

    # Confirm type distinction
    assert EACCESAccessDeniedError != ENOENTNotFoundError
    assert not issubclass(ENOENTNotFoundError, EACCESAccessDeniedError)


def test_14_source_matrix_generation_integrity() -> None:
    """Verify build_source_scope_and_authority_matrix() returns structured matrix with 16 items and 5 questions."""
    matrix = build_source_scope_and_authority_matrix()
    assert matrix["task_id"] == TASK_ID
    assert matrix["controller_dispatch_sha"] == CONTROLLER_DISPATCH_SHA
    assert matrix["source_items_count"] == 16
    assert len(matrix["source_items"]) == 16
    assert len(matrix["rights_questionnaire"]) == 5

    # Check that six candidate months are present
    months_found = [
        item["relative_path"] for item in matrix["source_items"]
        if item["role"] == InstrumentRole.BTC_PERP_1M_KLINE.value
    ]
    assert len(months_found) == 6
    for path in SIX_NONPROTECTED_CANDIDATE_PATHS:
        assert path in months_found


def test_15_audit_receipt_serialization() -> None:
    """Verify AuditReceipt serializes cleanly to JSON without errors."""
    accounting = SyscallAccounting(lstat_calls=5, total_calls=5)
    receipt = AuditReceipt(
        receipt_id="rcpt_test_001",
        task_id=TASK_ID,
        timestamp_utc="2026-10-10T12:00:00Z",
        requested_path="research/BTCUSDT/1m/year=2021/month=03/data.parquet",
        canonical_relative_path="research/BTCUSDT/1m/year=2021/month=03/data.parquet",
        requested_level=AccessLevel.L1_METADATA,
        decision=PolicyDecision.PERMITTED,
        reason="Test approval",
        syscall_accounting=accounting,
        metadata_size_bytes=2756024,
    )
    d = receipt.to_dict()
    serialized = json.dumps(d, indent=2)
    assert "rcpt_test_001" in serialized
    assert "PERMITTED" in serialized
    assert d["syscall_accounting"]["lstat_calls"] == 5
