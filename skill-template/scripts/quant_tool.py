#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import urllib.error
import urllib.request


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser()
    sub = root.add_subparsers(dest="action", required=True)
    sub.add_parser("health")
    sub.add_parser("scan")
    sub.add_parser("latest")
    show = sub.add_parser("show")
    show.add_argument("signal_id")
    explain = sub.add_parser("explain")
    explain.add_argument("signal_id")
    decision = sub.add_parser("decision")
    decision.add_argument("signal_id")
    decision.add_argument("decision", choices=["accept", "ignore"])
    decision.add_argument("--entry", type=float)
    performance = sub.add_parser("performance")
    performance.add_argument("--days", type=int, default=30)
    sub.add_parser("execution-status")
    execution_plan = sub.add_parser("execution-plan")
    execution_plan.add_argument("signal_id")
    execution_submit = sub.add_parser("execution-submit")
    execution_submit.add_argument("plan_id")
    execution_submit.add_argument("--confirm", required=True)
    execution_reconcile = sub.add_parser("execution-reconcile")
    execution_reconcile.add_argument("plan_id")
    execution_plan_close = sub.add_parser("execution-plan-close")
    execution_plan_close.add_argument("--symbol", default="BTCUSDT")
    execution_submit_close = sub.add_parser("execution-submit-close")
    execution_submit_close.add_argument("plan_id")
    execution_submit_close.add_argument("--confirm", required=True)
    execution_cancel = sub.add_parser("execution-cancel")
    execution_cancel.add_argument("plan_id")
    execution_cancel.add_argument("--confirm", required=True)
    return root


def api_call(base_url: str, args: argparse.Namespace) -> int:
    routes = {
        "health": ("GET", "/health", None),
        "scan": ("POST", "/scan", {}),
        "latest": ("GET", "/signals/latest", None),
        "show": ("GET", f"/signals/{getattr(args, 'signal_id', '')}", None),
        "explain": ("GET", f"/signals/{getattr(args, 'signal_id', '')}/explanation", None),
        "performance": (
            "GET",
            f"/performance?days={getattr(args, 'days', 30)}",
            None,
        ),
        "decision": (
            "POST",
            f"/signals/{getattr(args, 'signal_id', '')}/decision",
            {
                "decision": getattr(args, "decision", None),
                "actual_entry": getattr(args, "entry", None),
            },
        ),
        "execution-status": ("GET", "/execution/status", None),
        "execution-plan": (
            "POST",
            f"/execution/plans/entry/{getattr(args, 'signal_id', '')}",
            {},
        ),
        "execution-submit": (
            "POST",
            f"/execution/plans/{getattr(args, 'plan_id', '')}/submit",
            {"confirmation_hash": getattr(args, "confirm", "")},
        ),
        "execution-reconcile": (
            "POST",
            f"/execution/plans/{getattr(args, 'plan_id', '')}/reconcile",
            {},
        ),
        "execution-plan-close": (
            "POST",
            "/execution/close/preview",
            {"symbol": getattr(args, "symbol", "BTCUSDT")},
        ),
        "execution-submit-close": (
            "POST",
            f"/execution/close/{getattr(args, 'plan_id', '')}/submit",
            {"confirmation_hash": getattr(args, "confirm", "")},
        ),
        "execution-cancel": (
            "POST",
            f"/execution/plans/{getattr(args, 'plan_id', '')}/cancel",
            {"confirmation_hash": getattr(args, "confirm", "")},
        ),
    }
    method, path, payload = routes[args.action]
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        base_url.rstrip("/") + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            print(response.read().decode("utf-8"))
        return 0
    except urllib.error.HTTPError as exc:
        print(exc.read().decode("utf-8"))
        return 2
    except urllib.error.URLError as exc:
        print(json.dumps({"error": f"QuantCore API unavailable: {exc}"}))
        return 3


def cli_call(args: argparse.Namespace) -> int:
    executable = shutil.which("quantctl")
    if executable is None:
        print('{"error":"set BTC_QUANT_API_URL or install quantctl on PATH"}')
        return 127
    commands = {
        "health": [executable, "health"],
        "scan": [executable, "scan", "BTCUSDT"],
        "latest": [executable, "signal", "latest"],
        "show": [executable, "signal", "show", getattr(args, "signal_id", "")],
        "explain": [executable, "explain", getattr(args, "signal_id", "")],
        "performance": [executable, "performance", "--days", str(getattr(args, "days", 30))],
    }
    if args.action == "decision":
        command = [executable, "decision", args.signal_id, args.decision]
        if args.entry is not None:
            command.extend(["--entry", str(args.entry)])
    elif args.action == "execution-status":
        command = [executable, "execution", "status"]
    elif args.action == "execution-plan":
        command = [executable, "execution", "plan-entry", args.signal_id]
    elif args.action == "execution-submit":
        command = [executable, "execution", "submit", args.plan_id, "--confirm", args.confirm]
    elif args.action == "execution-reconcile":
        command = [executable, "execution", "reconcile", args.plan_id]
    elif args.action == "execution-plan-close":
        command = [executable, "execution", "plan-close", "--symbol", args.symbol]
    elif args.action == "execution-submit-close":
        command = [
            executable,
            "execution",
            "submit-close",
            args.plan_id,
            "--confirm",
            args.confirm,
        ]
    elif args.action == "execution-cancel":
        command = [
            executable,
            "execution",
            "cancel",
            args.plan_id,
            "--confirm",
            args.confirm,
        ]
    else:
        command = commands[args.action]
    return subprocess.run(command, check=False).returncode


def main() -> int:
    args = parser().parse_args()
    api_url = os.getenv("BTC_QUANT_API_URL")
    return api_call(api_url, args) if api_url else cli_call(args)


if __name__ == "__main__":
    raise SystemExit(main())
