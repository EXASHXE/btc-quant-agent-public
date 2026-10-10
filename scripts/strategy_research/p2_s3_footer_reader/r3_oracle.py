"""Independent synthetic R3 OS-boundary oracle; never opens a market data tree."""

from __future__ import annotations

import errno
import hashlib
import json
import os
import shutil
import tempfile
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any, Self

from scripts.strategy_research.p2_s3_footer_reader.constants import S3_SINGLE_PILOT_REL_PATH
from scripts.strategy_research.p2_s3_footer_reader.r3_native_probe import trace_own_child
from scripts.strategy_research.p2_s3_footer_reader.reader import SingleFileParquetFooterReader
from scripts.strategy_research.p2_s3_footer_reader.types import create_valid_synthetic_grant

_FIXTURES = Path(__file__).with_name("r3_fixtures.json")
_SHA = Path(__file__).with_name("r3_fixtures.sha256")
_OWNER_LITERAL = "/root/workspace/project/Quant-agent/data"  # string only.


def load_frozen_fixture() -> dict[str, Any]:
    raw = _FIXTURES.read_bytes()
    expected = _SHA.read_text().split()[0]
    if hashlib.sha256(raw).hexdigest() != expected:
        raise AssertionError("R3 fixture changed after freeze")
    fixture = json.loads(raw)
    if hashlib.sha256(bytes.fromhex(fixture["parquet_hex"])).hexdigest() != fixture["parquet_sha256"]:
        raise AssertionError("R3 synthetic bytes changed")
    return fixture


class BoundaryObserver:
    """Records real os.* calls, forwarding each invocation to the original API."""

    _FAMILIES = ("open", "fstat", "pread", "close", "stat", "lstat", "readlink")

    def __init__(self, *, native_close_fault: str | None = None,
                 native_open_fault_label: str | None = None,
                 native_pread_fault: bool = False,
                 fstat_fault: bool = False, short_pread: bool = False) -> None:
        self.native_close_fault = native_close_fault
        self.native_open_fault_label = native_open_fault_label
        self.native_pread_fault = native_pread_fault
        self.fstat_fault = fstat_fault
        self.short_pread = short_pread
        self.events: list[dict[str, Any]] = []
        self.owned: dict[int, str] = {}
        self._original: dict[str, Callable[..., Any]] = {}
        self._supports_dir_fd: set[Callable[..., Any]] | None = None
        self._supports_dir_fd_original: Any = None
        self._fault_done = False

    def __enter__(self) -> Self:
        self._supports_dir_fd_original = os.supports_dir_fd
        self._supports_dir_fd = set(os.supports_dir_fd)
        os.supports_dir_fd = self._supports_dir_fd
        for family in self._FAMILIES:
            original = getattr(os, family)
            self._original[family] = original

            def proxy(*args: Any, _family: str = family, **kwargs: Any) -> Any:
                return self._call(_family, *args, **kwargs)

            setattr(os, family, proxy)
            if original in os.supports_dir_fd:
                os.supports_dir_fd.add(proxy)
        return self

    def __exit__(self, *_exc: object) -> None:
        for family, original in self._original.items():
            setattr(os, family, original)
        os.supports_dir_fd = self._supports_dir_fd_original

    def _call(self, family: str, *args: Any, **kwargs: Any) -> Any:
        label = str(args[0]) if args else ""
        if family in ("fstat", "pread", "close") and args:
            label = self.owned.get(int(args[0]), f"fd:{args[0]}")
        event: dict[str, Any] = {"family": family, "label": label}
        self.events.append(event)
        try:
            if family == "open" and not self._fault_done and self.native_open_fault_label == label:
                self._fault_done = True
                return self._original[family](*args, **{**kwargs, "dir_fd": -1})
            if family == "close" and not self._fault_done and self.native_close_fault == label:
                self._fault_done = True
                # A genuine kernel EBADF entry on -1; the original FD remains owned.
                return self._original[family](-1)
            if family == "fstat" and self.fstat_fault and label.endswith("data.parquet") and not self._fault_done:
                self._fault_done = True
                return self._original[family](-1)
            if family == "pread" and self.short_pread and not self._fault_done:
                self._fault_done = True
                amount = max(0, int(args[1]) - 1)
                return self._original[family](args[0], amount, args[2])
            if family == "pread" and self.native_pread_fault and not self._fault_done:
                self._fault_done = True
                return self._original[family](-1, args[1], args[2])
            result = self._original[family](*args, **kwargs)
        except OSError as exc:
            event["errno"] = exc.errno
            raise
        event["errno"] = 0
        if family == "open":
            self.owned[int(result)] = label
            event["returned_fd"] = int(result)
        elif family == "close":
            self.owned.pop(int(args[0]), None)
        elif family == "pread":
            event["requested"] = int(args[1])
            event["offset"] = int(args[2])
            event["returned_bytes"] = len(result)
        return result

    def physically_held(self) -> list[dict[str, Any]]:
        """Confirm possible leaks after target scope; then cleanup using original close."""
        held: list[dict[str, Any]] = []
        for fd, label in list(self.owned.items()):
            try:
                self._original["fstat"](fd)
            except OSError as exc:
                if exc.errno != errno.EBADF:
                    raise
            else:
                held.append({"fd": fd, "label": label})
                self._original["close"](fd)
        return held


def _prepare_tree(case: dict[str, Any], parquet_bytes: bytes) -> tuple[Path, Path, Path]:
    base = Path(tempfile.mkdtemp(prefix="r3-native-", dir="/tmp"))
    base.chmod(0o755)
    cursor = base
    for index in range(int(case["depth"])):
        cursor = cursor / f"d{index}"
        cursor.mkdir(mode=0o755)
    root = cursor / "root"
    root.mkdir(mode=0o755)
    leaf = root / S3_SINGLE_PILOT_REL_PATH
    leaf.parent.mkdir(parents=True)
    leaf.write_bytes(parquet_bytes)
    kind = case["kind"]
    if kind == "missing_ancestor":
        shutil.rmtree(root / "research")
    elif kind == "symlink_ancestor":
        shutil.rmtree(root / "research")
        (root / "research").symlink_to(base)
    elif kind == "nondirectory_ancestor":
        shutil.rmtree(root / "research")
        (root / "research").write_text("synthetic non-directory")
    elif kind == "permission_eacces":
        (root / "research").chmod(0o000)
    elif kind == "symlink_leaf":
        leaf.unlink()
        other = base / "other_synthetic.parquet"
        other.write_bytes(parquet_bytes)
        leaf.symlink_to(other)
    elif kind == "hardlink_leaf":
        os.link(leaf, base / "hardlink_synthetic.parquet")
    elif kind == "leaf_swap":
        (base / "replacement_synthetic.parquet").write_bytes(parquet_bytes)
    elif kind == "footer_oversize":
        leaf.write_bytes(b"PAR1" + b"X" * 8 + (65_537).to_bytes(4, "little") + b"PAR1")
    elif kind == "footer_corrupt":
        leaf.write_bytes(b"PAR1" + b"X" * 32 + (32).to_bytes(4, "little") + b"PAR1")
    elif kind == "invalid_magic":
        leaf.write_bytes(parquet_bytes[:-4] + b"NOPE")
    return base, root, leaf


def run_case(case: dict[str, Any], *, fixture: dict[str, Any] | None = None) -> dict[str, Any]:
    """Execute one frozen case, compare independent boundary and native observations."""
    fixture = load_frozen_fixture() if fixture is None else fixture
    base, root, leaf = _prepare_tree(case, bytes.fromhex(fixture["parquet_hex"]))
    kind = str(case["kind"])
    root_arg = _OWNER_LITERAL if kind == "owner_literal" else str(root)

    def operation() -> tuple[dict[str, Any], BoundaryObserver]:
        fault = None
        if kind == "native_anchor_close_ebadf":
            fault = "/"
        elif kind == "native_leaf_close_ebadf":
            fault = "data.parquet"
        observer = BoundaryObserver(
            native_close_fault=fault,
            native_open_fault_label=("research" if kind == "native_unknown_open_ebadf" else None),
            native_pread_fault=kind == "native_pread_ebadf",
            fstat_fault=kind == "fstat_failure",
            short_pread=kind == "pread_short",
        )
        result: dict[str, Any]
        with observer:
            grant = None
            if kind != "missing_grant":
                grant = create_valid_synthetic_grant(
                    root_arg, max_attempted_fs_calls=int(case["cap"]),
                    attest_root_custody=kind != "self_minted_no_custody",
                    expires_at_epoch_s=(1_800_000_000 if kind == "expired_grant" else 1_900_000_000),
                )
            if kind == "wrong_grant" and grant is not None:
                grant = replace(grant, grant_id="wrong-id")
            if kind == "root_swap":
                os.rename(root, root.with_name("old_root"))
                root.mkdir()
            if kind == "leaf_swap":
                replacement = base / "replacement_synthetic.parquet"
            if kind == "permission_eacces" and os.geteuid() == 0:
                os.setgid(65534)
                os.setuid(65534)
            hook = None
            if kind == "leaf_swap":
                hook = lambda: os.rename(replacement, leaf)
            reader = SingleFileParquetFooterReader(
                synthetic_fixture_root=root_arg, grant=grant,
                post_trailer_pread_hook=hook,
                short_read_truncate_bytes=(1 if kind == "pread_short" else None),
                simulated_close_errno_by_label=(
                    {"data.parquet": errno.EIO} if kind == "preentry_close_failure" else None
                ),
                request_extra_row_page_read=kind == "extra_byte_request",
            )
            rel = (
                "research/BTCUSDT/1m/year=2026/month=03/data.parquet"
                if kind == "protected_target" else S3_SINGLE_PILOT_REL_PATH
            )
            try:
                receipt = reader.evaluate_to_receipt(rel)
                result = {"receipt": receipt.to_dict()}
            except BaseException as exc:  # noqa: BLE001 - raw errors are evidence.
                result = {"uncaught": f"{type(exc).__name__}: {exc}"}
        return result, observer

    def postprocess(observed: tuple[dict[str, Any], BoundaryObserver]) -> dict[str, Any]:
        result, observer = observed
        result["python_boundary_events"] = observer.events
        result["physically_held_fds_after_reader"] = observer.physically_held()
        result["native_close_fault_fired"] = observer._fault_done if kind.startswith("native_") else None
        return result

    try:
        traced = trace_own_child(operation, postprocess)
    finally:
        if kind == "permission_eacces":
            (root / "research").chmod(0o755)
        shutil.rmtree(base)
    boundary = traced["observation"]["python_boundary_events"]
    core_boundary = [e for e in boundary if e["family"] in ("open", "fstat", "pread", "close")
                     and not (e["family"] == "open" and e["label"] == "")]
    traced["python_core_total"] = len(core_boundary)
    traced["python_core_counts"] = {
        family: sum(e["family"] == family for e in core_boundary)
        for family in ("open", "fstat", "pread", "close")
    }
    return {"case": case, **traced}


def assert_case_contract(result: dict[str, Any]) -> None:
    """Independent observations must satisfy the R3 hard constraints."""
    case = result["case"]
    observation = result["observation"]
    assert result["child_exit_code"] == 0
    assert "uncaught" not in observation, observation.get("uncaught")
    receipt = observation["receipt"]
    accounting = receipt["syscall_accounting"]
    actual = result["native_core_total"]
    cap = int(case["cap"])
    assert actual <= cap, (case["id"], actual, cap)
    assert actual == result["python_core_total"], (case["id"], actual, result["python_core_total"])
    assert actual == accounting["attempted_fs_calls_total"], (case["id"], actual, accounting)
    for family, reported in (("open", "openat_attempted"), ("fstat", "fstat_attempted"),
                             ("pread", "pread_attempted"), ("close", "close_attempted")):
        assert result["native_core_counts"][family] == accounting[reported], (case["id"], family)
    assert accounting["owner_root_touched"] is False
    assert receipt["header_verification_status"] == "FILE_HEADER_NOT_VERIFIED"
    assert accounting["actual_read_bytes_total"] <= 65_544
    assert accounting["trailer_bytes_read"] <= 8
    assert accounting["footer_bytes_read"] <= 65_536
    assert all(event["family"] in {"rename", "renameat", "mkdir"}
               for event in result["native_noncore_fs_events"])
    native_preads = [event for event in result["native_core_events"]
                     if event["family"] == "pread"]
    assert len(native_preads) <= 2
    assert sum(event["arg2"] for event in native_preads) <= 65_544
    assert all((0 <= event["returned"] <= event["arg2"])
               or (event["returned"] == -event["errno"] and event["errno"] > 0)
               for event in native_preads)
    if receipt["file_size_bytes"] is not None:
        assert all(event["arg3"] >= 4 for event in native_preads)
    if receipt["allowed"]:
        assert receipt["schema_metadata"]["row_data_pages_read"] == 0
        text = json.dumps(receipt, sort_keys=True)
        assert "R3_SYNTHETIC_ONLY" not in text
        assert '"min"' not in text and '"max"' not in text
    if case["kind"] in ("native_anchor_close_ebadf", "native_leaf_close_ebadf"):
        assert observation["native_close_fault_fired"] is True
        held = observation["physically_held_fds_after_reader"]
        assert held, case["id"]
        assert receipt["allowed"] is False
        assert receipt["decision_code"] == "FD_CLOSE_UNCONFIRMED_FAIL_CLOSED"
        assert accounting["open_fds_remaining"] >= len(held)
        assert accounting["unconfirmed_fds"]
    if case["kind"] == "preentry_close_failure":
        assert accounting["simulated_pre_close_failures"] >= 1
        assert accounting["simulated_pre_close_failures"] == len(accounting["unconfirmed_fds"])
        assert accounting["unconfirmed_fds"]
        assert not any(event["family"] == "close" and event["label"] == "data.parquet"
                       for event in observation["python_boundary_events"])
        assert observation["physically_held_fds_after_reader"]
        assert receipt["decision_code"] == "FD_CLOSE_UNCONFIRMED_FAIL_CLOSED"
    if case["id"].startswith("normal_cap_") and cap < 36:
        assert receipt["allowed"] is False
    if case["kind"] in ("owner_literal", "protected_target", "missing_grant", "wrong_grant", "expired_grant"):
        assert receipt["allowed"] is False
    if case["kind"] == "normal" and cap == 100:
        assert receipt["allowed"] is (int(case["depth"]) <= 5)
    elif case["kind"] != "normal":
        assert receipt["allowed"] is False


def write_machine_results(path: Path) -> dict[str, Any]:
    fixture = load_frozen_fixture()
    outcomes = []
    for case in fixture["cases"]:
        result = run_case(case, fixture=fixture)
        assert_case_contract(result)
        outcomes.append(result)
    shallow = run_case(
        {"id": "matched_r2_shallow", "kind": "normal", "depth": 0, "cap": 100},
        fixture=fixture,
    )
    assert_case_contract(shallow)
    shallow_accounting = shallow["observation"]["receipt"]["syscall_accounting"]
    if (shallow["native_core_total"] != 50
            or shallow_accounting["preparation_attempted_fs_calls"] != 13
            or shallow_accounting["reader_attempted_fs_calls"] != 37):
        raise AssertionError("R2-matched shallow geometry changed")
    cross_fork = run_cross_fork_prepared_grant()
    if (cross_fork["child"]["native_core_total"] != 0
            or cross_fork["child"]["observation"]["receipt"]["allowed"]
            or not cross_fork["parent_receipt"]["allowed"]):
        raise AssertionError("cross-fork prepared grant replay was not denied")
    retuned_cap101 = run_second_use_or_retune("retune_cap101")
    retuned_receipt = retuned_cap101["observation"]["receipt"]
    if (retuned_cap101["native_core_total"] != 0
            or retuned_receipt["syscall_accounting"]["preparation_attempted_fs_calls"] <= 0
            or retuned_receipt["syscall_accounting"]["reader_attempted_fs_calls"] != 0):
        raise AssertionError("retuned grant hid prior preparation cost")
    prepared_platform = run_prepared_platform_denial()
    platform_accounting = prepared_platform["observation"]["receipt"]["syscall_accounting"]
    if (prepared_platform["native_core_total"] != 16
            or platform_accounting["attempted_fs_calls_total"] != 16
            or platform_accounting["reader_attempted_fs_calls"] != 0):
        raise AssertionError("platform denial hid prior preparation calls")
    payload = {
        "scope": "SYNTHETIC_TEMP_ONLY_NATIVE_OWN_CHILD",
        "fixture_sha256": hashlib.sha256(_FIXTURES.read_bytes()).hexdigest(),
        "parquet_sha256": fixture["parquet_sha256"],
        "case_count": len(outcomes),
        "results": outcomes,
        "matched_r2_shallow": shallow,
        "cross_fork_replay": cross_fork,
        "retuned_cap101_second_use_scope": retuned_cap101,
        "prepared_platform_failure": prepared_platform,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return payload


def run_second_use_or_retune(kind: str) -> dict[str, Any]:
    """Trace only the second read after untraced, explicitly reported preparation."""
    if kind not in {"reuse", "retune_cap", "retune_cap101", "retune_bytes"}:
        raise ValueError(kind)
    fixture = load_frozen_fixture()
    base, root, _leaf = _prepare_tree(
        {"kind": "normal", "depth": 1, "cap": 100}, bytes.fromhex(fixture["parquet_hex"])
    )
    state: dict[str, Any] = {}

    def prepare() -> None:
        grant = create_valid_synthetic_grant(str(root), max_attempted_fs_calls=100)
        state["grant"] = grant
        if kind == "reuse":
            state["first_receipt"] = SingleFileParquetFooterReader(
                synthetic_fixture_root=str(root), grant=grant
            ).evaluate_to_receipt().to_dict()

    def operation() -> tuple[dict[str, Any], BoundaryObserver]:
        grant = state["grant"]
        if kind == "retune_cap":
            grant = replace(grant, max_attempted_fs_calls=25, signature_hex="")
            grant = replace(grant, signature_hex=grant.compute_expected_checksum())
        elif kind == "retune_cap101":
            grant = replace(grant, max_attempted_fs_calls=101, signature_hex="")
            grant = replace(grant, signature_hex=grant.compute_expected_checksum())
        elif kind == "retune_bytes":
            grant = replace(grant, max_total_read_bytes=1, signature_hex="")
            grant = replace(grant, signature_hex=grant.compute_expected_checksum())
        observer = BoundaryObserver()
        with observer:
            receipt = SingleFileParquetFooterReader(
                synthetic_fixture_root=str(root), grant=grant
            ).evaluate_to_receipt()
            output = {"receipt": receipt.to_dict(), "first_receipt": state.get("first_receipt")}
        return output, observer

    def postprocess(observed: tuple[dict[str, Any], BoundaryObserver]) -> dict[str, Any]:
        output, observer = observed
        output["python_boundary_events"] = observer.events
        output["physically_held_fds_after_reader"] = observer.physically_held()
        return output

    try:
        return {"kind": kind, **trace_own_child(operation, postprocess, prepare=prepare)}
    finally:
        shutil.rmtree(base)


def run_cross_fork_prepared_grant() -> dict[str, Any]:
    """A grant prepared by the parent must not authorize its forked child."""
    fixture = load_frozen_fixture()
    base, root, _leaf = _prepare_tree(
        {"kind": "normal", "depth": 1, "cap": 100}, bytes.fromhex(fixture["parquet_hex"])
    )
    try:
        # Preparation takes place in this parent, before the tracer forks.
        grant = create_valid_synthetic_grant(str(root), max_attempted_fs_calls=100)

        def operation() -> tuple[dict[str, Any], BoundaryObserver]:
            observer = BoundaryObserver()
            with observer:
                receipt = SingleFileParquetFooterReader(
                    synthetic_fixture_root=str(root), grant=grant
                ).evaluate_to_receipt()
            return {"receipt": receipt.to_dict()}, observer

        def postprocess(observed: tuple[dict[str, Any], BoundaryObserver]) -> dict[str, Any]:
            result, observer = observed
            result["python_boundary_events"] = observer.events
            result["physically_held_fds_after_reader"] = observer.physically_held()
            return result

        child = trace_own_child(operation, postprocess)
        # The parent retains the sole original preparation and may consume it once.
        parent_receipt = SingleFileParquetFooterReader(
            synthetic_fixture_root=str(root), grant=grant
        ).evaluate_to_receipt().to_dict()
        return {"child": child, "parent_receipt": parent_receipt}
    finally:
        shutil.rmtree(base)


def run_constructor_denial(kind: str) -> dict[str, Any]:
    """Verify early constructor failures produce a zero-FS structured receipt."""
    if kind not in {"missing_pread", "invalid_101_call_budget"}:
        raise ValueError(kind)
    # This path is string-only: no fixture or source is opened in either case.
    root = "/tmp/r3-constructor-denial-synthetic-root"
    grant = create_valid_synthetic_grant(root, attest_root_custody=False)
    if kind == "invalid_101_call_budget":
        grant = replace(grant, max_attempted_fs_calls=101, signature_hex="")
        grant = replace(grant, signature_hex=grant.compute_expected_checksum())

    def operation() -> tuple[dict[str, Any], BoundaryObserver]:
        observer = BoundaryObserver()
        with observer:
            saved_pread = os.pread
            if kind == "missing_pread":
                del os.pread
            try:
                receipt = SingleFileParquetFooterReader(
                    synthetic_fixture_root=root, grant=grant
                ).evaluate_to_receipt()
                result: dict[str, Any] = {"receipt": receipt.to_dict()}
            except BaseException as exc:  # noqa: BLE001 - raw errors prove failure.
                result = {"uncaught": f"{type(exc).__name__}: {exc}"}
            finally:
                os.pread = saved_pread
        return result, observer

    def postprocess(observed: tuple[dict[str, Any], BoundaryObserver]) -> dict[str, Any]:
        result, observer = observed
        result["python_boundary_events"] = observer.events
        result["physically_held_fds_after_reader"] = observer.physically_held()
        return result

    return {"kind": kind, **trace_own_child(operation, postprocess)}


def run_prepared_platform_denial() -> dict[str, Any]:
    """Preparation's real calls remain visible if platform capability then vanishes."""
    fixture = load_frozen_fixture()
    base, root, _leaf = _prepare_tree(
        {"kind": "normal", "depth": 1, "cap": 100}, bytes.fromhex(fixture["parquet_hex"])
    )

    def operation() -> tuple[dict[str, Any], BoundaryObserver]:
        observer = BoundaryObserver()
        with observer:
            grant = create_valid_synthetic_grant(str(root), max_attempted_fs_calls=100)
            saved_pread = os.pread
            del os.pread
            try:
                receipt = SingleFileParquetFooterReader(
                    synthetic_fixture_root=str(root), grant=grant
                ).evaluate_to_receipt()
                output: dict[str, Any] = {"receipt": receipt.to_dict()}
            except BaseException as exc:  # noqa: BLE001 - raw error is regression evidence.
                output = {"uncaught": f"{type(exc).__name__}: {exc}"}
            finally:
                os.pread = saved_pread
        return output, observer

    def postprocess(observed: tuple[dict[str, Any], BoundaryObserver]) -> dict[str, Any]:
        output, observer = observed
        output["python_boundary_events"] = observer.events
        output["physically_held_fds_after_reader"] = observer.physically_held()
        return output

    try:
        return trace_own_child(operation, postprocess)
    finally:
        shutil.rmtree(base)


if __name__ == "__main__":
    destination = Path(
        "evidence/v0.6/b_line/p2_s3_footer_reader_r1/"
        "S3A_R3_NATIVE_SYSCALL_AND_FD_RESULTS.json"
    )
    summary = write_machine_results(destination)
    print(json.dumps({"case_count": summary["case_count"], "destination": str(destination)}))
