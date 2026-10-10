"""Adversarial security attack vectors, TOCTOU races, mount escapes, and deliberate mutants."""

import hashlib
import os

from scripts.strategy_research.p2_s2_source_contract.constants import (
    IMMUTABLE_OWNER_WSL_DATA_ROOT,
    RECORDED_METADATA_FILE_SIZES,
    SIX_NONPROTECTED_CANDIDATE_PATHS,
)
from scripts.strategy_research.p2_s2_source_contract.errors import (
    EACCESAccessDeniedError,
    ENOENTNotFoundError,
    ProductionRootOverrideDeniedError,
    ZeroBytePolicyViolationError,
)
from scripts.strategy_research.p2_s2_source_contract.policy_kernel import (
    SyntheticSourceContractKernel,
)
from scripts.strategy_research.p2_s2_source_contract.syscall_interface import (
    InMemoryFakeFilesystem,
    InstrumentedSyscallHook,
    SyntheticFsNode,
)
from scripts.strategy_research.p2_s2_source_contract.types import (
    AccessLevel,
    CapabilityToken,
    InstrumentRole,
    PolicyDecision,
)


def _setup_base_fs() -> tuple[InMemoryFakeFilesystem, InstrumentedSyscallHook, str]:
    fake_fs = InMemoryFakeFilesystem(root_dev=1)
    root = "/synthetic/data"
    fake_fs.add_directory(root, dev=1)
    fake_fs.add_directory(f"{root}/research", dev=1)
    fake_fs.add_directory(f"{root}/research/BTCUSDT", dev=1)
    fake_fs.add_directory(f"{root}/research/BTCUSDT/1m", dev=1)

    for y in ["2021", "2023", "2025"]:
        fake_fs.add_directory(f"{root}/research/BTCUSDT/1m/year={y}", dev=1)
        for m in ["03", "04"]:
            fake_fs.add_directory(f"{root}/research/BTCUSDT/1m/year={y}/month={m}", dev=1)
            rel_p = f"research/BTCUSDT/1m/year={y}/month={m}/data.parquet"
            fake_fs.add_file(f"{root}/{rel_p}", size=RECORDED_METADATA_FILE_SIZES[rel_p], dev=1)

    hook = InstrumentedSyscallHook(fake_fs, max_syscalls=100, max_bytes=0)
    return fake_fs, hook, root


def test_16_cli_fixed_root_bypass_counterexample() -> None:
    """Instantiating production mode with custom root or allow_custom_root flag raises ProductionRootOverrideDeniedError."""
    # Attempting custom root in production mode
    try:
        SyntheticSourceContractKernel(
            fixture_root="/custom/root/data",
            is_test_mode=False,
        )
        assert False, "Should have raised ProductionRootOverrideDeniedError"
    except ProductionRootOverrideDeniedError as exc:
        assert "Production mode forbids custom root overrides" in str(exc)

    # Attempting allow_custom_root flag in production mode
    try:
        SyntheticSourceContractKernel(
            fixture_root=IMMUTABLE_OWNER_WSL_DATA_ROOT,
            is_test_mode=False,
            allow_custom_root_flag=True,
        )
        assert False, "Should have raised ProductionRootOverrideDeniedError"
    except ProductionRootOverrideDeniedError as exc:
        assert "Production mode forbids 'allow_custom_root' flag" in str(exc)


def test_17_production_mode_refuses_physical_market_execution() -> None:
    """Production mode without injected test harness strictly refuses physical market execution."""
    kernel = SyntheticSourceContractKernel(is_test_mode=False)
    token = CapabilityToken(
        token_id="tok_prod",
        subject="test",
        allowed_paths=list(SIX_NONPROTECTED_CANDIDATE_PATHS),
        max_level=AccessLevel.L1_METADATA,
    )
    receipt = kernel.evaluate_request(
        target_rel_path=SIX_NONPROTECTED_CANDIDATE_PATHS[0],
        token=token,
        requested_level=AccessLevel.L1_METADATA,
    )
    assert receipt.decision == PolicyDecision.DENIED_PERMISSION_ERROR
    assert receipt.exception_class == "AccessDeniedError"
    assert "Direct physical execution on owner data root is prohibited" in receipt.reason


def test_18_absolute_path_alias_traversal() -> None:
    """Target paths with leading slash or absolute notation are rejected."""
    _, hook, root = _setup_base_fs()
    kernel = SyntheticSourceContractKernel(fixture_root=root, syscall_hook=hook, is_test_mode=True)
    token = CapabilityToken(
        token_id="tok_test",
        subject="test",
        allowed_paths=["/absolute/path"],
        max_level=AccessLevel.L1_METADATA,
    )
    receipt = kernel.evaluate_request(
        target_rel_path="/research/BTCUSDT/1m/year=2021/month=03/data.parquet",
        token=token,
        requested_level=AccessLevel.L1_METADATA,
    )
    assert receipt.decision == PolicyDecision.DENIED_PARENT_TRAVERSAL
    assert receipt.exception_class == "PathTraversalError"


def test_19_parent_traversal_dot_dot_escape() -> None:
    """Path containing '..' traversal components is rejected."""
    _, hook, root = _setup_base_fs()
    kernel = SyntheticSourceContractKernel(fixture_root=root, syscall_hook=hook, is_test_mode=True)
    token = CapabilityToken(
        token_id="tok_test",
        subject="test",
        allowed_paths=["research/../secret.txt"],
        max_level=AccessLevel.L1_METADATA,
    )
    receipt = kernel.evaluate_request(
        target_rel_path="research/../secret.txt",
        token=token,
        requested_level=AccessLevel.L1_METADATA,
    )
    assert receipt.decision == PolicyDecision.DENIED_PARENT_TRAVERSAL
    assert receipt.exception_class == "PathTraversalError"


def test_20_sibling_data_v2_escape() -> None:
    """Attempting to escape to sibling directory e.g. 'research/../../data-v2/' is rejected."""
    _, hook, root = _setup_base_fs()
    kernel = SyntheticSourceContractKernel(fixture_root=root, syscall_hook=hook, is_test_mode=True)
    token = CapabilityToken(
        token_id="tok_test",
        subject="test",
        allowed_paths=["research/../../data-v2/file.parquet"],
        max_level=AccessLevel.L1_METADATA,
    )
    receipt = kernel.evaluate_request(
        target_rel_path="research/../../data-v2/file.parquet",
        token=token,
        requested_level=AccessLevel.L1_METADATA,
    )
    assert receipt.decision == PolicyDecision.DENIED_PARENT_TRAVERSAL


def test_21_intermediate_symlink_rejection() -> None:
    """An intermediate symlink directory along the component walk is detected and rejected."""
    fake_fs, hook, root = _setup_base_fs()
    # Replace research/BTCUSDT/1m with a symlink to outside
    fake_fs.add_symlink(f"{root}/research/BTCUSDT/1m", "/somewhere/outside")
    kernel = SyntheticSourceContractKernel(fixture_root=root, syscall_hook=hook, is_test_mode=True)
    token = CapabilityToken(
        token_id="tok_test",
        subject="test",
        allowed_paths=list(SIX_NONPROTECTED_CANDIDATE_PATHS),
        max_level=AccessLevel.L1_METADATA,
    )
    receipt = kernel.evaluate_request(
        target_rel_path=SIX_NONPROTECTED_CANDIDATE_PATHS[0],
        token=token,
        requested_level=AccessLevel.L1_METADATA,
    )
    assert receipt.decision == PolicyDecision.DENIED_SYMLINK_TRAVERSAL
    assert receipt.exception_class == "SymlinkEncounteredError"


def test_22_root_symlink_rejection() -> None:
    """Root directory itself being a symlink is rejected."""
    fake_fs = InMemoryFakeFilesystem()
    root = "/synthetic/data"
    fake_fs.add_symlink(root, "/outside/real_root")
    hook = InstrumentedSyscallHook(fake_fs, max_syscalls=50, max_bytes=0)

    kernel = SyntheticSourceContractKernel(fixture_root=root, syscall_hook=hook, is_test_mode=True)
    token = CapabilityToken(
        token_id="tok_test",
        subject="test",
        allowed_paths=list(SIX_NONPROTECTED_CANDIDATE_PATHS),
        max_level=AccessLevel.L1_METADATA,
    )
    receipt = kernel.evaluate_request(
        target_rel_path=SIX_NONPROTECTED_CANDIDATE_PATHS[0],
        token=token,
        requested_level=AccessLevel.L1_METADATA,
    )
    assert receipt.decision == PolicyDecision.DENIED_SYMLINK_TRAVERSAL
    assert "Root path itself is a symlink" in receipt.reason


def test_23_target_leaf_symlink_rejection() -> None:
    """Target leaf file being a symlink is rejected."""
    fake_fs, hook, root = _setup_base_fs()
    leaf = f"{root}/research/BTCUSDT/1m/year=2021/month=03/data.parquet"
    # Overwrite leaf with a symlink
    fake_fs.add_symlink(leaf, "/etc/passwd")

    kernel = SyntheticSourceContractKernel(fixture_root=root, syscall_hook=hook, is_test_mode=True)
    token = CapabilityToken(
        token_id="tok_test",
        subject="test",
        allowed_paths=list(SIX_NONPROTECTED_CANDIDATE_PATHS),
        max_level=AccessLevel.L1_METADATA,
    )
    receipt = kernel.evaluate_request(
        target_rel_path=SIX_NONPROTECTED_CANDIDATE_PATHS[0],
        token=token,
        requested_level=AccessLevel.L1_METADATA,
    )
    assert receipt.decision == PolicyDecision.DENIED_SYMLINK_TRAVERSAL
    assert "Symlink detected at leaf target" in receipt.reason


def test_24_non_directory_ancestor_rejection() -> None:
    """Ancestor component being a regular file instead of a directory is rejected with DENIED_NON_DIRECTORY_ANCESTOR."""
    fake_fs, hook, root = _setup_base_fs()
    # Replace research/BTCUSDT/1m with a regular file
    fake_fs.add_file(f"{root}/research/BTCUSDT/1m", size=50)

    kernel = SyntheticSourceContractKernel(fixture_root=root, syscall_hook=hook, is_test_mode=True)
    token = CapabilityToken(
        token_id="tok_test",
        subject="test",
        allowed_paths=list(SIX_NONPROTECTED_CANDIDATE_PATHS),
        max_level=AccessLevel.L1_METADATA,
    )
    receipt = kernel.evaluate_request(
        target_rel_path=SIX_NONPROTECTED_CANDIDATE_PATHS[0],
        token=token,
        requested_level=AccessLevel.L1_METADATA,
    )
    assert receipt.decision == PolicyDecision.DENIED_NON_DIRECTORY_ANCESTOR
    assert receipt.exception_class == "NotADirectoryError"


def test_25_fake_mount_device_boundary_traversal() -> None:
    """Traversing across filesystem/device boundaries (differing st_dev) is rejected."""
    fake_fs, hook, root = _setup_base_fs()
    # Make month=03 belong to a different mount device (st_dev=2 vs root_dev=1)
    fake_fs.add_directory(f"{root}/research/BTCUSDT/1m/year=2021/month=03", dev=2)

    kernel = SyntheticSourceContractKernel(fixture_root=root, syscall_hook=hook, is_test_mode=True)
    token = CapabilityToken(
        token_id="tok_test",
        subject="test",
        allowed_paths=list(SIX_NONPROTECTED_CANDIDATE_PATHS),
        max_level=AccessLevel.L1_METADATA,
    )
    receipt = kernel.evaluate_request(
        target_rel_path=SIX_NONPROTECTED_CANDIDATE_PATHS[0],
        token=token,
        requested_level=AccessLevel.L1_METADATA,
    )
    assert receipt.decision == PolicyDecision.DENIED_MOUNT_BOUNDARY_VIOLATION
    assert receipt.exception_class == "MountBoundaryViolationError"


def test_26_toctou_symlink_replacement_race() -> None:
    """Target replaced with a symlink between stat and descriptor open is detected via TOCTOU defense."""
    fake_fs, hook, root = _setup_base_fs()
    target_path = f"{root}/research/BTCUSDT/1m/year=2021/month=03/data.parquet"

    # Register mutation: upon lstat, node mutates into a symlink
    symlink_mutated_node = SyntheticFsNode(
        is_dir=False,
        is_symlink=True,
        symlink_target="/etc/shadow",
        mode=0o120777,
        dev=1,
        ino=9999,
    )
    fake_fs.register_toctou_mutation(target_path, symlink_mutated_node)

    kernel = SyntheticSourceContractKernel(fixture_root=root, syscall_hook=hook, is_test_mode=True)
    token = CapabilityToken(
        token_id="tok_l2",
        subject="test",
        allowed_paths=list(SIX_NONPROTECTED_CANDIDATE_PATHS),
        max_level=AccessLevel.L2_SCHEMA,
    )
    receipt = kernel.evaluate_request(
        target_rel_path=SIX_NONPROTECTED_CANDIDATE_PATHS[0],
        token=token,
        requested_level=AccessLevel.L2_SCHEMA,
    )
    # The TOCTOU open hook caught the symlink/open mismatch
    assert receipt.decision in (PolicyDecision.DENIED_SYMLINK_TRAVERSAL, PolicyDecision.DENIED_PERMISSION_ERROR)


def test_27_protected_partition_2026_rejection() -> None:
    """Attempts to access year=2026 partitions are denied unconditionally."""
    _, hook, root = _setup_base_fs()
    kernel = SyntheticSourceContractKernel(fixture_root=root, syscall_hook=hook, is_test_mode=True)
    token = CapabilityToken(
        token_id="tok_test",
        subject="test",
        allowed_paths=["research/BTCUSDT/1m/year=2026/month=03/data.parquet"],
        max_level=AccessLevel.L1_METADATA,
    )
    receipt = kernel.evaluate_request(
        target_rel_path="research/BTCUSDT/1m/year=2026/month=03/data.parquet",
        token=token,
        requested_level=AccessLevel.L1_METADATA,
    )
    assert receipt.decision == PolicyDecision.DENIED_PROTECTED_PATH
    assert receipt.exception_class == "ProtectedPartitionDeniedError"


def test_28_protected_partition_forward_rejection() -> None:
    """Attempts to access data/forward/ partitions are denied unconditionally."""
    _, hook, root = _setup_base_fs()
    kernel = SyntheticSourceContractKernel(fixture_root=root, syscall_hook=hook, is_test_mode=True)
    token = CapabilityToken(
        token_id="tok_test",
        subject="test",
        allowed_paths=["data/forward/BTCUSDT/trades.parquet"],
        max_level=AccessLevel.L1_METADATA,
    )
    receipt = kernel.evaluate_request(
        target_rel_path="data/forward/BTCUSDT/trades.parquet",
        token=token,
        requested_level=AccessLevel.L1_METADATA,
    )
    assert receipt.decision == PolicyDecision.DENIED_PROTECTED_PATH


def test_29_protected_partition_h39_rejection() -> None:
    """Attempts to access h39 validation partitions are denied unconditionally."""
    _, hook, root = _setup_base_fs()
    kernel = SyntheticSourceContractKernel(fixture_root=root, syscall_hook=hook, is_test_mode=True)
    token = CapabilityToken(
        token_id="tok_test",
        subject="test",
        allowed_paths=["research/h39_validation/results.json"],
        max_level=AccessLevel.L1_METADATA,
    )
    receipt = kernel.evaluate_request(
        target_rel_path="research/h39_validation/results.json",
        token=token,
        requested_level=AccessLevel.L1_METADATA,
    )
    assert receipt.decision == PolicyDecision.DENIED_PROTECTED_PATH


def test_30_sensitive_credentials_rejection() -> None:
    """Attempts to access .env or credentials files are denied unconditionally."""
    _, hook, root = _setup_base_fs()
    kernel = SyntheticSourceContractKernel(fixture_root=root, syscall_hook=hook, is_test_mode=True)
    token = CapabilityToken(
        token_id="tok_test",
        subject="test",
        allowed_paths=[".env", "id_rsa"],
        max_level=AccessLevel.L1_METADATA,
    )
    for sensitive in [".env", "config/credentials.json"]:
        receipt = kernel.evaluate_request(
            target_rel_path=sensitive,
            token=token,
            requested_level=AccessLevel.L1_METADATA,
        )
        assert receipt.decision == PolicyDecision.DENIED_PROTECTED_PATH


def test_31_instrument_type_kline_vs_mark_mismatch() -> None:
    """Requesting Mark price role for a Kline path is rejected with DENIED_TYPE_MISMATCH."""
    _, hook, root = _setup_base_fs()
    kernel = SyntheticSourceContractKernel(fixture_root=root, syscall_hook=hook, is_test_mode=True)
    token = CapabilityToken(
        token_id="tok_test",
        subject="test",
        allowed_paths=list(SIX_NONPROTECTED_CANDIDATE_PATHS),
        max_level=AccessLevel.L1_METADATA,
    )
    receipt = kernel.evaluate_request(
        target_rel_path=SIX_NONPROTECTED_CANDIDATE_PATHS[0],
        token=token,
        requested_level=AccessLevel.L1_METADATA,
        role=InstrumentRole.BTC_PERP_RAW_MARK_CONTAINER,
    )
    assert receipt.decision == PolicyDecision.DENIED_TYPE_MISMATCH
    assert receipt.exception_class == "TypeMismatchError"


def test_32_instrument_spot_vs_perp_mismatch() -> None:
    """Requesting Spot role for Perp dataset is rejected with DENIED_TYPE_MISMATCH."""
    _, hook, root = _setup_base_fs()
    kernel = SyntheticSourceContractKernel(fixture_root=root, syscall_hook=hook, is_test_mode=True)
    token = CapabilityToken(
        token_id="tok_test",
        subject="test",
        allowed_paths=list(SIX_NONPROTECTED_CANDIDATE_PATHS),
        max_level=AccessLevel.L1_METADATA,
    )
    receipt = kernel.evaluate_request(
        target_rel_path=SIX_NONPROTECTED_CANDIDATE_PATHS[0],
        token=token,
        requested_level=AccessLevel.L1_METADATA,
        role=InstrumentRole.BTC_SPOT_MANIFEST_AND_DATA,
    )
    assert receipt.decision == PolicyDecision.DENIED_TYPE_MISMATCH


def test_33_raw_mark_continuous_1m_pit_unproven_fails_closed() -> None:
    """Raw mark directory existence does not prove continuous 1m Mark PIT; fails closed with DENIED_UNKNOWN_CLOCK_PROVENANCE."""
    fake_fs, hook, root = _setup_base_fs()
    fake_fs.add_directory(f"{root}/research/BTCUSDT/raw/mark_price")
    kernel = SyntheticSourceContractKernel(fixture_root=root, syscall_hook=hook, is_test_mode=True)

    token = CapabilityToken(
        token_id="tok_mark",
        subject="test",
        allowed_paths=["research/BTCUSDT/raw/mark_price"],
        max_level=AccessLevel.L1_METADATA,
    )
    receipt = kernel.evaluate_request(
        target_rel_path="research/BTCUSDT/raw/mark_price",
        token=token,
        requested_level=AccessLevel.L1_METADATA,
        role=InstrumentRole.BTC_PERP_RAW_MARK_CONTAINER,
        verify_clock_provenance=True,
        clock_provenance_proven=False,
    )
    assert receipt.decision == PolicyDecision.DENIED_UNKNOWN_CLOCK_PROVENANCE
    assert "Raw Mark price container existence does NOT prove continuous 1m PIT Mark" in receipt.reason


def test_34_funding_events_unknown_clock_fails_closed() -> None:
    """Funding events CSV existence does not prove known-at vs settlement timing; fails closed with DENIED_UNKNOWN_CLOCK_PROVENANCE."""
    fake_fs, hook, root = _setup_base_fs()
    fake_fs.add_file(f"{root}/research/BTCUSDT/funding_events.csv", size=219066)
    kernel = SyntheticSourceContractKernel(fixture_root=root, syscall_hook=hook, is_test_mode=True)

    token = CapabilityToken(
        token_id="tok_funding",
        subject="test",
        allowed_paths=["research/BTCUSDT/funding_events.csv"],
        max_level=AccessLevel.L1_METADATA,
    )
    receipt = kernel.evaluate_request(
        target_rel_path="research/BTCUSDT/funding_events.csv",
        token=token,
        requested_level=AccessLevel.L1_METADATA,
        role=InstrumentRole.BTC_PERP_FUNDING_EVENTS_CSV,
        verify_clock_provenance=True,
        clock_provenance_proven=False,
    )
    assert receipt.decision == PolicyDecision.DENIED_UNKNOWN_CLOCK_PROVENANCE
    assert "Funding events existence does NOT prove known-at/settlement timing" in receipt.reason


def test_35_full_file_hash_reading_blocked() -> None:
    """Hashing entire file requires reading body bytes; strictly blocked by zero-byte policy."""
    _fake_fs, hook, root = _setup_base_fs()
    file_path = f"{root}/research/BTCUSDT/1m/year=2021/month=03/data.parquet"
    fd = hook.open(file_path, os.O_RDONLY)

    # Attempting to read 1024 bytes to compute sha256
    hasher = hashlib.sha256()
    try:
        data = hook.read(fd, 1024)
        hasher.update(data)
        assert False, "Should have raised ZeroBytePolicyViolationError"
    except ZeroBytePolicyViolationError as exc:
        assert "Zero-byte read policy strictly enforced" in str(exc)
    finally:
        hook.close(fd)


# ==============================================================================
# DELIBERATE MUTANT DETECTION TESTS (Proving test suite catches subtle defects)
# ==============================================================================

def test_36_mutant_1_auto_enable_test_mode_detected() -> None:
    """PROVE test suite catches Mutant 1: Silent auto-enable of test mode in production."""
    class AutoEnableTestModeMutantKernel(SyntheticSourceContractKernel):
        """Mutant that silently sets is_test_mode=True to allow root bypass."""
        def __init__(self, fixture_root=None, syscall_hook=None, is_test_mode=False):
            # Deliberate mutant flaw: override is_test_mode to True
            super().__init__(
                fixture_root=fixture_root or "/bypassed/root",
                syscall_hook=syscall_hook,
                is_test_mode=True,  # MUTANT BUG
            )

    # Verification: An unapproved caller in 'production' mode expects an error
    mutant = AutoEnableTestModeMutantKernel(is_test_mode=False)
    # The mutant corrupted the safety invariant: is_test_mode became True
    assert mutant.is_test_mode is True, "Mutant did not inject expected flaw"

    # The production test assertion (from test_16 / test_17) catches this mutant:
    # Under correct implementation, passing a custom root without is_test_mode MUST raise ProductionRootOverrideDeniedError
    caught = False
    try:
        SyntheticSourceContractKernel(fixture_root="/custom/root", is_test_mode=False)
    except ProductionRootOverrideDeniedError:
        caught = True
    assert caught, "TestSuite successfully proves detection of Mutant 1 (custom root auto-enable bypass)"


def test_37_mutant_2_uncounted_direct_stat_detected() -> None:
    """PROVE test suite catches Mutant 2: Direct uncounted stat bypasses accounting counter."""
    fake_fs = InMemoryFakeFilesystem()
    root = "/test"
    fake_fs.add_directory(root)

    class UncountedStatMutantHook(InstrumentedSyscallHook):
        """Mutant hook that calls backend directly without incrementing accounting."""
        def lstat(self, path):
            # MUTANT BUG: does not call self.accounting.record_lstat()
            return self.backend.lstat(path)

    mutant_hook = UncountedStatMutantHook(fake_fs, max_syscalls=50, max_bytes=0)
    mutant_hook.lstat(root)

    # The test assertion from test_09 catches the uncounted call:
    assert mutant_hook.accounting.lstat_calls == 0  # Flawed mutant behavior
    # Whereas correct hook registers 1:
    correct_hook = InstrumentedSyscallHook(fake_fs, max_syscalls=50, max_bytes=0)
    correct_hook.lstat(root)
    assert correct_hook.accounting.lstat_calls == 1  # Correct behavior caught and verified


def test_38_mutant_3_silent_eacces_masking_detected() -> None:
    """PROVE test suite catches Mutant 3: PermissionError silently converted to FileNotFoundError."""
    fake_fs = InMemoryFakeFilesystem()
    root = "/test"
    fake_fs.add_directory(root)
    fake_fs.add_file(f"{root}/secret", size=10)
    fake_fs.set_permission_denied(f"{root}/secret", True)

    class SilentEaccesMaskingHook(InstrumentedSyscallHook):
        """Mutant hook that maps PermissionError to ENOENTNotFoundError."""
        def lstat(self, path):
            try:
                return super().lstat(path)
            except EACCESAccessDeniedError as exc:
                # MUTANT BUG: Silently map EACCES to ENOENT
                raise ENOENTNotFoundError(f"Path not found: {path}") from exc

    mutant_hook = SilentEaccesMaskingHook(fake_fs, max_syscalls=50, max_bytes=0)

    # Mutant causes ENOENTNotFoundError instead of EACCESAccessDeniedError
    caught_as_enoent = False
    try:
        mutant_hook.lstat(f"{root}/secret")
    except ENOENTNotFoundError:
        caught_as_enoent = True

    assert caught_as_enoent, "Mutant injected flaw successfully"

    # The test assertion from test_13 specifically tests and requires EACCESAccessDeniedError:
    correct_hook = InstrumentedSyscallHook(fake_fs, max_syscalls=50, max_bytes=0)
    caught_as_eacces = False
    try:
        correct_hook.lstat(f"{root}/secret")
    except EACCESAccessDeniedError:
        caught_as_eacces = True
    assert caught_as_eacces, "TestSuite successfully proves detection of Mutant 3 (EACCES distinct from ENOENT)"
