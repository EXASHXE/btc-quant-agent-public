from __future__ import annotations

import os
import shutil
import socket
import sqlite3
import subprocess
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

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
            "--property=ActiveState,SubState,UnitFileState,Result,NextElapseUSecRealtime",
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
        }
    return results


def check_network_proxy() -> dict[str, Any]:
    http_proxy = os.environ.get("http_proxy") or os.environ.get("HTTP_PROXY")
    https_proxy = os.environ.get("https_proxy") or os.environ.get("HTTPS_PROXY")
    all_proxy = os.environ.get("all_proxy") or os.environ.get("ALL_PROXY")

    # Probe proxy port 7897 (or configured proxy port)
    proxy_port = 7897
    proxy_open = False
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(2.0)
    try:
        sock.connect(("127.0.0.1", proxy_port))
        proxy_open = True
    except OSError:
        proxy_open = False
    finally:
        sock.close()

    # Probe Binance public API
    binance_status = "UNKNOWN"
    binance_detail = ""
    target_url = "https://fapi.binance.com/fapi/v1/ping"
    try:
        req = Request(target_url, headers={"User-Agent": "btc-quant-agent/0.3.20"})
        with urlopen(req, timeout=5.0) as resp:
            if resp.status == 200:
                binance_status = "OK"
                binance_detail = "reachable"
            else:
                binance_status = f"HTTP_{resp.status}"
                binance_detail = str(resp.read().decode("utf-8", errors="replace"))
    except HTTPError as exc:
        if exc.code == 451:
            binance_status = "HTTP_451_REGION_RESTRICTED"
            binance_detail = "Binance rejected request: Service unavailable from restricted location (switch proxy away from US)."
        else:
            binance_status = f"HTTP_{exc.code}"
            binance_detail = str(exc.read().decode("utf-8", errors="replace"))
    except Exception as exc:  # noqa: BLE001
        binance_status = "NETWORK_ERROR"
        binance_detail = f"{type(exc).__name__}: {exc}"

    return {
        "http_proxy": http_proxy,
        "https_proxy": https_proxy,
        "all_proxy": all_proxy,
        "proxy_port_7897_open": proxy_open,
        "binance_reachability": binance_status,
        "binance_detail": binance_detail,
    }


def check_chains_and_storage(
    *,
    derivatives_store_path: str | Path = "data/forward/BTCUSDT/derivatives.sqlite3",
    opportunity_store_path: str | Path = "data/forward/BTCUSDT/opportunity_shadow.sqlite3",
    microstructure_root: str | Path = "data/forward/BTCUSDT/microstructure",
) -> dict[str, Any]:
    # Derivatives
    deriv_path = Path(derivatives_store_path)
    latest_deriv_slot: int | None = None
    latest_deriv_status: str | None = None
    if deriv_path.exists():
        try:
            conn = sqlite3.connect(deriv_path, timeout=5.0)
            row = conn.execute(
                "SELECT scheduled_slot_ms, status FROM collection_runs WHERE scheduled_slot_ms IS NOT NULL ORDER BY scheduled_slot_ms DESC LIMIT 1"
            ).fetchone()
            if row:
                latest_deriv_slot, latest_deriv_status = int(row[0]), str(row[1])
            conn.close()
        except Exception as exc:  # noqa: BLE001
            latest_deriv_status = f"ERROR: {exc}"

    # Opportunity
    opp_path = Path(opportunity_store_path)
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
            conn.close()
        except Exception as exc:  # noqa: BLE001
            latest_opp_status = f"ERROR: {exc}"

    # Microstructure
    micro_path = Path(microstructure_root)
    latest_heartbeat_ms: int | None = None
    if micro_path.exists():
        for p in micro_path.glob("microstructure-*.sqlite3"):
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
        },
        "opportunity": {
            "store_path": str(opp_path),
            "latest_slot_ms": latest_opp_slot,
            "latest_status": latest_opp_status,
        },
        "microstructure": {
            "root": str(micro_path),
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
    if epoch_reg.exists():
        reg = EvidenceEpochRegistry.load(epoch_reg)
        active_entries = [
            e for e in reg.entries if e.formal_eligibility_role == "FORMAL_ACTIVE"
        ]
        terminal_entries = [
            e for e in reg.entries if "TERMINAL" in e.formal_eligibility_role
        ]
        derivatives_info = {
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
                {"epoch_id": e.epoch_id, "terminal_reason": e.terminal_reason}
                for e in terminal_entries
            ],
        }

    opportunity_info: dict[str, Any] = {}
    if opp_reg.exists():
        reg_opp = OpportunityCampaignRegistry.load(opp_reg)
        opportunity_info = {
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
            ]
        }

    return {
        "derivatives_epochs": derivatives_info,
        "opportunity_campaigns": opportunity_info,
    }


def forward_doctor() -> dict[str, Any]:
    wsl_info = check_wsl_systemd()
    unit_info = check_systemd_units()
    net_info = check_network_proxy()
    chain_info = check_chains_and_storage()
    campaign_info = check_campaign_states()

    # Evaluate overall doctor health
    healthy = True
    issues: list[str] = []

    if not wsl_info["linger_enabled"]:
        issues.append("WSL user linger is disabled (loginctl enable-linger)")
    if net_info["binance_reachability"] == "HTTP_451_REGION_RESTRICTED":
        issues.append("Binance endpoints blocked by HTTP 451: Proxy is routed through restricted US node")
        healthy = False
    elif net_info["binance_reachability"] != "OK":
        issues.append(f"Binance reachability failed: {net_info['binance_reachability']}")
        healthy = False

    # Check units
    for unit_name, details in unit_info.items():
        if unit_name.endswith(".timer") and details["active_state"] != "active":
            issues.append(f"Timer {unit_name} is not active ({details['active_state']})")
            healthy = False
        if unit_name == "btc-quant-microstructure-forward.service" and details["active_state"] != "active":
            issues.append(f"Microstructure service is not active ({details['active_state']})")
            healthy = False

    return {
        "status": "HEALTHY" if healthy and not issues else "DEGRADED",
        "issues": issues,
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
