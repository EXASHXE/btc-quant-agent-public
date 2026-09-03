from __future__ import annotations

import os
import re
import shutil
import socket
import sqlite3
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request

from .evidence_epoch import EvidenceEpochRegistry
from .opportunity_forward import OpportunityCampaignRegistry


def _run_cmd(args: list[str]) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        return proc.returncode, proc.stdout.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        return -1, str(exc)


def check_wsl_systemd() -> dict[str, Any]:
    is_wsl = (
        Path("/proc/sys/fs/binfmt_misc/WSLInterop").exists()
        or "microsoft" in Path("/proc/version").read_text().lower()
        if Path("/proc/version").exists()
        else False
    )
    code, out = _run_cmd(["systemctl", "--user", "is-system-running"])
    systemd_running = code == 0 or out in {"running", "degraded"}

    user = os.environ.get("USER", "root")
    _code_linger, out_linger = _run_cmd(["loginctl", "show-user", user, "--property=Linger"])
    linger_enabled = "Linger=yes" in out_linger

    return {
        "is_wsl": is_wsl,
        "systemd_running": systemd_running,
        "systemd_state": out,
        "user": user,
        "linger_enabled": linger_enabled,
    }


def check_systemd_units() -> dict[str, dict[str, Any]]:
    units = [
        "btc-quant-forward-derivatives.timer",
        "btc-quant-forward-derivatives.service",
        "btc-quant-opportunity-forward.timer",
        "btc-quant-opportunity-forward.service",
        "btc-quant-opportunity-resolve.timer",
        "btc-quant-opportunity-resolve.service",
        "btc-quant-forward-health.timer",
        "btc-quant-forward-health.service",
        "btc-quant-microstructure-forward.service",
    ]
    results: dict[str, dict[str, Any]] = {}
    for unit in units:
        _code, out = _run_cmd([
            "systemctl",
            "--user",
            "show",
            unit,
            "--property=ActiveState,SubState,UnitFileState,Result,NextElapseUSecRealtime,ExecStart",
        ])
        props: dict[str, str] = {}
        for line in out.splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                props[k] = v
        results[unit] = {
            "active_state": props.get("ActiveState", "unknown"),
            "sub_state": props.get("SubState", "unknown"),
            "unit_file_state": props.get("UnitFileState", "unknown"),
            "result": props.get("Result", "unknown"),
            "next_elapse_usec": props.get("NextElapseUSecRealtime", ""),
            "exec_start": props.get("ExecStart", ""),
        }
    return results


def check_collector_resolver_parity(unit_info: dict[str, dict[str, Any]]) -> dict[str, Any]:
    opp_forward = unit_info.get("btc-quant-opportunity-forward.service", {}).get("exec_start", "")
    opp_resolve = unit_info.get("btc-quant-opportunity-resolve.service", {}).get("exec_start", "")

    parity_ok = True
    reason = "Collector and resolver use aligned campaign resolution"
    if opp_forward and opp_resolve:
        reg_f = re.search(r"--registry\s+(\S+)", opp_forward)
        reg_r = re.search(r"--registry\s+(\S+)", opp_resolve)
        camp_f = re.search(r"--campaign\s+(\S+)", opp_forward)
        camp_r = re.search(r"--campaign\s+(\S+)", opp_resolve)

        target_f = reg_f.group(1) if reg_f else (camp_f.group(1) if camp_f else None)
        target_r = reg_r.group(1) if reg_r else (camp_r.group(1) if camp_r else None)

        if target_f and target_r and target_f != target_r:
            parity_ok = False
            reason = f"Collector targets '{target_f}' but resolver targets '{target_r}'"
        elif bool(reg_f) != bool(reg_r):
            parity_ok = False
            reason = "Collector and resolver use mismatched resolution mechanisms (registry vs campaign)"

    return {
        "parity_ok": parity_ok,
        "detail": reason,
    }


def check_network_proxy(*, url_opener: Any = None) -> dict[str, Any]:
    http_proxy = os.environ.get("http_proxy") or os.environ.get("HTTP_PROXY")
    https_proxy = os.environ.get("https_proxy") or os.environ.get("HTTPS_PROXY")
    all_proxy = os.environ.get("all_proxy") or os.environ.get("ALL_PROXY")

    # Test port 7897 connectivity
    port_open = False
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2.0)
        port_open = sock.connect_ex(("127.0.0.1", 7897)) == 0
        sock.close()
    except Exception:  # noqa: BLE001
        port_open = False

    # Test Binance endpoint reachability and detect HTTP 451 (US geoblock)
    binance_status = "UNKNOWN"
    binance_detail = ""
    try:
        req = Request(
            "https://fapi.binance.com/fapi/v1/time",
            headers={"User-Agent": "btc-quant-agent/0.3.21"},
        )
        opener = url_opener or urllib.request.urlopen
        with opener(req, timeout=5.0) as resp:
            code = getattr(resp, "status", getattr(resp, "code", 200))
            if code == 200:
                binance_status = "OK"
                binance_detail = "reachable"
            else:
                binance_status = f"HTTP_{code}"
                binance_detail = f"unexpected HTTP status {code}"
    except HTTPError as exc:
        if exc.code == 451:
            binance_status = "HTTP_451_REGION_RESTRICTED"
            binance_detail = (
                "Binance rejected request: Service unavailable from restricted location (switch proxy away from US)."
            )
        else:
            binance_status = f"HTTP_{exc.code}"
            binance_detail = f"HTTP error: {exc.code} {exc.reason}"
    except URLError as exc:
        binance_status = "CONNECTION_ERROR"
        binance_detail = f"network error: {exc.reason}"
    except Exception as exc:  # noqa: BLE001
        binance_status = "ERROR"
        binance_detail = f"probe exception: {type(exc).__name__}: {exc}"

    return {
        "http_proxy": http_proxy,
        "https_proxy": https_proxy,
        "all_proxy": all_proxy,
        "proxy_port_7897_open": port_open,
        "binance_reachability": binance_status,
        "binance_detail": binance_detail,
    }


def check_chains_and_storage(
    *,
    derivatives_store_path: str | Path = "data/forward/BTCUSDT/derivatives.sqlite3",
    opportunity_store_path: str | Path = "data/forward/BTCUSDT/opportunity_shadow.sqlite3",
    microstructure_root: str | Path = "data/forward/BTCUSDT/microstructure",
) -> dict[str, Any]:
    deriv_path = Path(derivatives_store_path)
    opp_path = Path(opportunity_store_path)

    latest_deriv_slot: int | None = None
    latest_deriv_status: str | None = None
    sqlite_integrity: dict[str, str] = {}
    if deriv_path.exists():
        try:
            conn = sqlite3.connect(deriv_path, timeout=5.0)
            row = conn.execute(
                "SELECT scheduled_slot_ms, status FROM collection_runs ORDER BY scheduled_slot_ms DESC LIMIT 1"
            ).fetchone()
            if row:
                latest_deriv_slot = int(row[0]) if row[0] is not None else None
                latest_deriv_status = str(row[1])
            chk = conn.execute("PRAGMA quick_check").fetchone()
            sqlite_integrity["derivatives"] = str(chk[0]) if chk else "ok"
            conn.close()
        except Exception as exc:  # noqa: BLE001
            latest_deriv_status = f"ERROR: {exc}"
            sqlite_integrity["derivatives"] = f"ERROR: {exc}"
    else:
        sqlite_integrity["derivatives"] = "FILE_NOT_FOUND"

    latest_opp_slot: int | None = None
    latest_opp_status: str | None = None
    if opp_path.exists():
        try:
            conn = sqlite3.connect(opp_path, timeout=5.0)
            row = conn.execute(
                "SELECT scheduled_slot_ms, status FROM scan_observations ORDER BY scheduled_slot_ms DESC LIMIT 1"
            ).fetchone()
            if row:
                latest_opp_slot, latest_opp_status = int(row[0]), str(row[1])
            chk = conn.execute("PRAGMA quick_check").fetchone()
            sqlite_integrity["opportunity"] = str(chk[0]) if chk else "OK"
            conn.close()
        except Exception as exc:  # noqa: BLE001
            latest_opp_status = f"ERROR: {exc}"
            sqlite_integrity["opportunity"] = f"ERROR: {exc}"
    else:
        sqlite_integrity["opportunity"] = "FILE_NOT_FOUND"

    # Microstructure
    micro_path = Path(microstructure_root)
    latest_heartbeat_ms: int | None = None
    micro_partition_count = 0
    total_micro_bytes = 0
    if micro_path.exists():
        for p in micro_path.glob("microstructure-*.sqlite3"):
            micro_partition_count += 1
            total_micro_bytes += p.stat().st_size
            try:
                conn = sqlite3.connect(p, timeout=5.0)
                row = conn.execute("SELECT MAX(last_heartbeat_ms) FROM process_instances").fetchone()
                if row and row[0] is not None:
                    measured = int(row[0])
                    latest_heartbeat_ms = max(latest_heartbeat_ms or measured, measured)
                conn.close()
            except Exception:  # noqa: BLE001,S110
                pass

    now_ms = int(time.time() * 1000)
    heartbeat_age_sec = (
        (now_ms - latest_heartbeat_ms) / 1000 if latest_heartbeat_ms is not None else None
    )

    # Disk usage
    check_dir = deriv_path.parent if deriv_path.parent.exists() else Path(".")
    total_bytes, _, free_bytes = shutil.disk_usage(check_dir)

    # Writable check
    writable = os.access(check_dir, os.W_OK)

    return {
        "derivatives": {
            "store_path": str(deriv_path),
            "latest_slot_ms": latest_deriv_slot,
            "latest_status": latest_deriv_status,
            "sqlite_integrity": sqlite_integrity.get("derivatives", "UNKNOWN"),
        },
        "opportunity": {
            "store_path": str(opp_path),
            "latest_slot_ms": latest_opp_slot,
            "latest_status": latest_opp_status,
            "sqlite_integrity": sqlite_integrity.get("opportunity", "UNKNOWN"),
        },
        "microstructure": {
            "root": str(micro_path),
            "partition_count": micro_partition_count,
            "total_size_mb": round(total_micro_bytes / (1024**2), 2),
            "latest_heartbeat_ms": latest_heartbeat_ms,
            "heartbeat_age_seconds": heartbeat_age_sec,
        },
        "storage": {
            "free_gb": round(free_bytes / (1024**3), 2),
            "total_gb": round(total_bytes / (1024**3), 2),
            "writable": writable,
        },
    }


def check_campaign_states(
    *,
    epoch_registry_path: str | Path = "configs/forward/derivatives_evidence_epochs.json",
    opportunity_registry_path: str | Path = "configs/forward/opportunity_forward_campaigns.json",
) -> dict[str, Any]:
    epoch_reg = Path(epoch_registry_path)
    opp_reg = Path(opportunity_registry_path)
    now_ms = int(time.time() * 1000)

    derivatives_info: dict[str, Any] = {}
    has_active_derivatives = False
    if epoch_reg.exists():
        reg = EvidenceEpochRegistry.load(epoch_reg)
        active_entries = [
            e
            for e in reg.entries
            if e.formal_eligibility_role in {"FORMAL_ACTIVE", "FORMAL_SUCCESSOR_PENDING"}
            and e.status not in {"FAILED_GAP_GATE_TERMINAL", "CANCELLED_BEFORE_START"}
        ]
        terminal_entries = [
            e
            for e in reg.entries
            if "TERMINAL" in e.formal_eligibility_role
            or e.status in {"FAILED_GAP_GATE_TERMINAL", "CANCELLED_BEFORE_START"}
        ]
        has_active_derivatives = len(active_entries) > 0
        derivatives_info = {
            "has_active_or_preregistered": has_active_derivatives,
            "active_or_preregistered": [
                {
                    "epoch_id": e.epoch_id,
                    "start_ms": e.start_ms,
                    "status": e.status,
                    "role": e.formal_eligibility_role,
                    "starts_in_seconds": max(0.0, (e.start_ms - now_ms) / 1000),
                }
                for e in active_entries
            ],
            "terminal_archives": [
                {"epoch_id": e.epoch_id, "terminal_reason": e.terminal_reason, "status": e.status}
                for e in terminal_entries
            ],
        }

    opportunity_info: dict[str, Any] = {}
    has_active_opportunity = False
    if opp_reg.exists():
        reg_opp = OpportunityCampaignRegistry.load(opp_reg)
        active_opp = [
            c
            for c in reg_opp.campaigns
            if c.formal_role in {"FORMAL_SUCCESSOR_ACTIVE", "FORMAL_SUCCESSOR_PENDING"}
            and c.status not in {"DATA_QUALITY_TERMINAL_ARCHIVE", "FAILED_GAP_GATE_TERMINAL"}
        ]
        has_active_opportunity = len(active_opp) > 0
        opportunity_info = {
            "has_active_or_preregistered": has_active_opportunity,
            "active_or_preregistered": [
                {
                    "campaign_id": c.campaign_id,
                    "start_ms": c.start_ms,
                    "status": c.status,
                    "role": c.formal_role,
                    "hypothesis_id": c.hypothesis_id,
                    "starts_in_seconds": max(0.0, (c.start_ms - now_ms) / 1000),
                }
                for c in active_opp
            ],
            "terminal_archives": [
                {
                    "campaign_id": c.campaign_id,
                    "hypothesis_id": c.hypothesis_id,
                    "status": c.status,
                    "role": c.formal_role,
                    "terminal_reason": c.terminal_reason,
                }
                for c in reg_opp.campaigns
                if c.formal_role in {"DATA_QUALITY_AT_RISK_ARCHIVE", "DATA_QUALITY_TERMINAL_ARCHIVE"}
            ],
            "campaigns": [
                {
                    "campaign_id": c.campaign_id,
                    "start_ms": c.start_ms,
                    "status": c.status,
                    "role": c.formal_role,
                    "hypothesis_id": c.hypothesis_id,
                    "starts_in_seconds": max(0.0, (c.start_ms - now_ms) / 1000),
                }
                for c in reg_opp.campaigns
            ],
        }

    return {
        "derivatives_epochs": derivatives_info,
        "opportunity_campaigns": opportunity_info,
        "has_active_derivatives": has_active_derivatives,
        "has_active_opportunity": has_active_opportunity,
    }


def forward_doctor(*, url_opener: Any = None) -> dict[str, Any]:
    wsl_info = check_wsl_systemd()
    unit_info = check_systemd_units()
    parity_info = check_collector_resolver_parity(unit_info)
    net_info = check_network_proxy(url_opener=url_opener)
    chain_info = check_chains_and_storage()
    campaign_info = check_campaign_states()

    issues: list[str] = []
    health_state = "HEALTHY"

    # 1. NETWORK_INELIGIBLE
    if net_info["binance_reachability"] == "HTTP_451_REGION_RESTRICTED":
        health_state = "NETWORK_INELIGIBLE"
        issues.append("Binance endpoints blocked by HTTP 451: Proxy is routed through restricted US node")
    elif net_info["binance_reachability"] != "OK":
        health_state = "NETWORK_INELIGIBLE"
        issues.append(f"Binance reachability failed: {net_info['binance_reachability']}")

    # 2. STORAGE_AT_RISK
    if not chain_info["storage"]["writable"]:
        health_state = "STORAGE_AT_RISK"
        issues.append("Storage directory is not writable")
    if chain_info["storage"]["free_gb"] < 2.0:
        health_state = "STORAGE_AT_RISK"
        issues.append(f"Storage free space critically low: {chain_info['storage']['free_gb']} GB (< 2 GB)")
    elif chain_info["storage"]["free_gb"] < 10.0:
        issues.append(f"Storage free space warning: {chain_info['storage']['free_gb']} GB (< 10 GB)")

    # 3. HOST_LIFECYCLE_AT_RISK
    if not wsl_info["linger_enabled"]:
        if health_state == "HEALTHY":
            health_state = "HOST_LIFECYCLE_AT_RISK"
        issues.append("WSL user linger is disabled (loginctl enable-linger)")
    if not wsl_info["systemd_running"]:
        if health_state == "HEALTHY":
            health_state = "HOST_LIFECYCLE_AT_RISK"
        issues.append("WSL systemd is not running")

    # 4. CONFIGURATION_INCONSISTENT
    if not parity_info["parity_ok"]:
        if health_state == "HEALTHY":
            health_state = "CONFIGURATION_INCONSISTENT"
        issues.append(f"Collector/resolver parity mismatch: {parity_info['detail']}")

    # 5. SQLite integrity
    for chain_name, key in [("Derivatives", "derivatives"), ("Opportunity", "opportunity")]:
        integ = chain_info[key].get("sqlite_integrity", "ok")
        if integ.lower() not in {"ok", "file_not_found"}:
            if health_state == "HEALTHY":
                health_state = "STORAGE_AT_RISK"
            issues.append(f"{chain_name} SQLite integrity failure: {integ}")

    # 6. Check units (SERVICE_UNHEALTHY)
    for unit_name, details in unit_info.items():
        if unit_name.endswith(".timer") and details["active_state"] != "active":
            if health_state == "HEALTHY":
                health_state = "SERVICE_UNHEALTHY"
            issues.append(f"Timer {unit_name} is not active ({details['active_state']})")
        if unit_name == "btc-quant-microstructure-forward.service" and details["active_state"] != "active":
            if health_state == "HEALTHY":
                health_state = "SERVICE_UNHEALTHY"
            issues.append(f"Microstructure service is not active ({details['active_state']})")

    # Microstructure heartbeat check
    hb_age = chain_info["microstructure"].get("heartbeat_age_seconds")
    if hb_age is not None and hb_age > 300.0:
        if health_state == "HEALTHY":
            health_state = "SERVICE_UNHEALTHY"
        issues.append(f"Microstructure heartbeat is stale: {hb_age:.1f}s (> 300s)")

    # 7. Evaluate campaign health state
    has_active_d = campaign_info.get("has_active_derivatives", False)
    has_active_o = campaign_info.get("has_active_opportunity", False)

    if health_state == "HEALTHY":
        if not has_active_d and not has_active_o:
            health_state = "FORWARD_DATA_INSUFFICIENT"
            issues.append(
                "All registered Derivatives and Opportunity chains are terminal archives. No active successor is accumulating."
            )
        else:
            active_d_list = campaign_info.get("derivatives_epochs", {}).get("active_or_preregistered", [])
            active_o_list = campaign_info.get("opportunity_campaigns", {}).get("active_or_preregistered", [])
            future_d = any(item.get("starts_in_seconds", 0.0) > 0 for item in active_d_list)
            future_o = any(item.get("starts_in_seconds", 0.0) > 0 for item in active_o_list)
            if future_d or future_o:
                health_state = "PREREGISTERED_NOT_STARTED"
            else:
                health_state = "HEALTHY_ACCUMULATING"

    return {
        "status": health_state,
        "is_healthy": health_state in {"HEALTHY", "HEALTHY_ACCUMULATING", "PREREGISTERED_NOT_STARTED"},
        "health_state": health_state,
        "issues": issues,
        "parity": parity_info,
        "wsl_systemd": wsl_info,
        "systemd_units": unit_info,
        "network": net_info,
        "chains": chain_info,
        "campaigns": campaign_info,
        "safety_invariants": {
            "execution": "DISABLED",
            "final_holdout": "SEALED",
            "qualified_direction_engine": "NONE",
            "strategy": "EXPERIMENTAL",
            "immutable_evidence_policy": "NO_BACKFILL_OR_HISTORY_REWRITE",
        },
    }


def recover_services(*, dry_run: bool = False) -> dict[str, Any]:
    user = os.environ.get("USER", "root")
    commands = [
        ["systemctl", "--user", "daemon-reload"],
        ["systemctl", "--user", "reset-failed"],
        ["systemctl", "--user", "enable", "--now", "btc-quant-forward-derivatives.timer"],
        ["systemctl", "--user", "enable", "--now", "btc-quant-opportunity-forward.timer"],
        ["systemctl", "--user", "enable", "--now", "btc-quant-opportunity-resolve.timer"],
        ["systemctl", "--user", "enable", "--now", "btc-quant-forward-health.timer"],
        ["systemctl", "--user", "restart", "btc-quant-microstructure-forward.service"],
    ]

    actions_planned: list[str] = [" ".join(cmd) for cmd in commands]
    actions_executed: list[dict[str, Any]] = []

    if not dry_run:
        # Check linger and enable if needed
        _run_cmd(["loginctl", "enable-linger", user])
        for cmd in commands:
            code, out = _run_cmd(cmd)
            actions_executed.append({
                "command": " ".join(cmd),
                "returncode": code,
                "output": out,
            })

    return {
        "dry_run": dry_run,
        "actions_planned": actions_planned,
        "actions_executed": actions_executed,
        "status": "DRY_RUN_COMPLETE" if dry_run else "RECOVERY_EXECUTED",
        "invariants_preserved": {
            "historical_data_mutated": False,
            "slots_backfilled": False,
            "campaign_starts_moved": False,
            "holdout_accessed": False,
            "execution_enabled": False,
        },
    }
