"""Bounded synthetic exercise and restart entry points."""

import argparse
import asyncio
import json
import os
import re
import sys
from contextlib import contextmanager
from pathlib import Path

from quant_hermes_feishu_h2b.explainer_gate import ScriptedModelResponse
from quant_hermes_feishu_h2b.outbound_sender import deterministic_feishu_uuid
from quant_personal_live_public_b5.contract import QA
from quant_personal_live_public_b5.decision import DecisionJournal, engine, replay

from .agent import configure
from .delivery import Delivery
from .facade import serving
from .inbound import PrivateDm, binding, mock_callback
from .safety import (
    Blocked,
    OfflinePermit,
    exclusive,
    isolated,
    private_directory,
    restrict_python_network,
)
from .source import FixtureCase, actionability, offline_adapter, refresh_interface
from .telemetry import Measurements, correlate, pi_export

WORKSPACE_PATTERN = re.compile(
    r"\.?lt-v080-(?:sol62-h3-hermes-quant-field-trial-01|[a-z0-9-]*h3[a-z0-9-]*review[a-z0-9-]*)"
)
CONFIG = """plugins:
  enabled:
    - quant-v080-h2b-readonly
memory:
  memory_enabled: false
  user_profile_enabled: false
compression:
  enabled: false
agent:
  environment_probe: false
model:
  context_length: 131072
"""


@contextmanager
def working(path):
    start = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(start)


def write_json(path, content):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(content, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")


def detail(client, card):
    response = client.call_tool(
        "get_signal_detail",
        {
            "episode_id": card["episode_id"],
            "card_id": card["card_id"],
            "as_of_ms": card["evaluated_ms"],
        },
    )
    if response["status"] != "OK":
        raise Blocked("T0_FACADE_VERIFICATION_FAILED")
    return response["data"]["snapshot"]


def synthetic_permit(root, now):
    return OfflinePermit(root, starts_ms=now - 1, expires_ms=now + 120_000, clock=lambda: now)


def composition(root, measurements):
    configure(root / "hermes")
    traces = {}
    for name, canary in (("canary", True), ("staged", False)):
        case = FixtureCase(root / name, measurements, canary=canary)
        with case.collecting():
            case.evaluate()
        traces[name] = case.trace

    case = FixtureCase(root / "pullback-long", measurements, "trend_pullback-long")
    permit = synthetic_permit(root, 1_735_700_000_000)
    with case.collecting():
        case.evaluate(0)
        (card,) = case.evaluate(1)
        cutoff = card["evaluated_ms"]
        key = case.trace[-1]["measurement_key"]
        with serving(case.source, case.journal) as client:
            original_version = detail(client, card)["card_version"]
            delivery = Delivery(
                root / "sender", binding(), root / "hermes", client, permit, measurements
            )
            alerts = []
            if card["market_status"] == "EXECUTABLE":
                selection = (card["episode_id"], card["card_id"])
                enqueue = delivery.enqueue(*selection, now_ms=cutoff, correlation=key)
                duplicate = delivery.enqueue(*selection, now_ms=cutoff, correlation=key)
                attempted = delivery.dispatch(now_ms=cutoff + 1, correlation=key)
                if (
                    not duplicate["deduplicated"]
                    or attempted["state"] != "PROVIDER_ACK"
                    or not delivery.sender.transport.used_hermes_adapter
                    or delivery.mock.requests[0]["uuid"]
                    != deterministic_feishu_uuid(enqueue["event_id"])
                ):
                    raise Blocked("SOURCE_TO_DM_INCOMPLETE")
                alerts.append(
                    {
                        "event_id": enqueue["event_id"],
                        "card_version": original_version,
                        "state": attempted["state"],
                        "deduplicated": duplicate["deduplicated"],
                        "human_read": "UNOBSERVED",
                        "evidence": QA,
                    }
                )

            async def chat():
                dm = PrivateDm(root, client, permit, delivery, measurements)
                cases = (
                    (1, "当前机会", None),
                    (2, f"查看 {card['episode_id']}", ScriptedModelResponse()),
                    (3, f"查看 {card['episode_id']}", ScriptedModelResponse(mode="quota")),
                    (4, f"查看 {card['episode_id']}", ScriptedModelResponse(mode="timeout")),
                    (5, f"查看 {card['episode_id']}", ScriptedModelResponse(mode="hallucinated")),
                )
                return [
                    await dm.handle(
                        mock_callback(number=number, text=text, ts=cutoff),
                        now_ms=cutoff,
                        as_of_ms=cutoff,
                        script=script,
                    )
                    for number, text, script in cases
                ]

            turn_results = asyncio.run(chat())
            provider = delivery.mock.requests
        (five,) = case.evaluate(2)
        (ten,) = case.evaluate(3, quote="chase")
    traces["pullback-long"] = case.trace
    write_json(root / "actionability.json", actionability(card, original_version, [five, ten]))
    write_json(root / "source-trace.json", traces)
    write_json(
        root / "transcripts.json",
        {
            "classification": QA,
            "alerts": alerts,
            "replies": turn_results,
            "mock_provider_requests": provider,
        },
    )
    recovery_case(root, measurements)


def recovery_case(root, measurements):
    case = FixtureCase(root / "early-long", measurements, "early_continuation-long")
    with case.collecting():
        case.evaluate(0)
        (card,) = case.evaluate(1)
    permit = synthetic_permit(root, 1_735_700_000_000)
    cutoff = card["evaluated_ms"]
    key = case.trace[-1]["measurement_key"]
    with serving(case.source, case.journal) as client:
        delivery = Delivery(
            root / "recovery", binding(), root / "hermes", client, permit, measurements
        )
        alert = delivery.enqueue(
            card["episode_id"], card["card_id"], now_ms=cutoff, correlation=key
        )
        attempt = delivery.dispatch(now_ms=cutoff + 1, correlation=key, crash=True)
        if attempt["state"] != "ATTEMPTED" or len(delivery.mock.requests) != 1:
            raise Blocked("CRASH_EXERCISE_DID_NOT_DISPATCH")
        write_json(
            root / "recovery-intent.json",
            {
                "cutoff_ms": cutoff,
                "event_id": alert["event_id"],
                "correlation": key,
                "mock_ack_lost": attempt["provider_result_lost_before_commit"],
            },
        )


def resume(root, measurements):
    intent = json.loads((root / "recovery-intent.json").read_text())
    key = intent["correlation"]
    measurements.record("RESTART", key)
    measurements.record("RECOVERY_BEGIN", key)
    permit = synthetic_permit(root, 1_735_700_000_001)
    case = root / "early-long"
    with serving(case / "source.sqlite", case / "journal.sqlite") as client:
        delivery = Delivery(
            root / "recovery", binding(), root / "hermes", client, permit, measurements
        )
        now = intent["cutoff_ms"] + 2_000
        reclaimed = delivery.sender.reclaim_unknown_deliveries(now_ms=now)
        if reclaimed != [intent["event_id"]]:
            raise Blocked("DELIVERY_RECOVERY_WITNESS_MISMATCH")
        measurements.record("DELIVERY_FAILURE", key, code="UNKNOWN_DELIVERY")
        if delivery.dispatch(now_ms=now, correlation=key) is not None or delivery.mock.requests:
            raise Blocked("UNSAFE_AUTOMATIC_REDELIVERY")
        ack = delivery.sender.reconcile_unknown(
            event_id=intent["event_id"],
            delivered=True,
            provider_message_id=intent["mock_ack_lost"],
            reconciled_at_ms=now + 1,
        )
        write_json(
            root / "recovery.json",
            {
                "classification": QA,
                "event_id": intent["event_id"],
                "reclaimed_to": "UNKNOWN_DELIVERY",
                "automatic_resends": len(delivery.mock.requests),
                "reconciled_state": ack["state"],
                "transitions": delivery.sender.outbox.get_transitions(intent["event_id"]),
                "human_read": "UNOBSERVED",
            },
        )
    measurements.record("RECOVERY_END", key)


def rebuild(root):
    results = []
    for name in ("pullback-long", "early-long", "staged"):
        case = root / name
        adapter = offline_adapter(case / "source.sqlite")
        saved = DecisionJournal(case / "journal.sqlite")
        output = case / "rebuild.sqlite"
        if output.exists():
            raise Blocked("REPLAY_OUTPUT_ALREADY_EXISTS")
        evaluator = engine(adapter, output)
        with saved.connect() as db:
            rows = list(db.execute("SELECT id FROM cards ORDER BY as_of,id"))
        for row in rows:
            card = saved.read(card_id=row[0])
            proof = replay(adapter, card)
            reprice = card["reprice"]
            args = {}
            if reprice is not None:
                args = {
                    "reprice_minutes": reprice["requested_delay_minutes"],
                    "episode_id": card["episode_id"],
                }
            rebuilt = evaluator.evaluate(
                card["symbol"],
                scan=card["evaluation_receipt"]["source_scan_id"],
                as_of_ms=card["evaluated_ms"],
                **args,
            )
            card.pop("journal_recorded_wall_ms")
            rebuilt.pop("journal_recorded_wall_ms")
            if card != rebuilt:
                raise Blocked("CAUSAL_REPLAY_MISMATCH")
            results.append({"case": name, **proof, "unchanged_decision_payload": True})
    write_json(root / "raw-replay.json", results)


def check_root(root):
    if root.parent.name not in {"workspaces"} or not WORKSPACE_PATTERN.fullmatch(root.name):
        raise Blocked("RUN_MUST_BE_IN_H3_WORKSPACE")
    private_directory(root)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="quant-hermes-h3")
    parser.add_argument(
        "mode", choices=("demo", "resume", "replay", "gate-status", "refresh-status")
    )
    parser.add_argument("--run-id", default="qa-run")
    args = parser.parse_args(argv)
    if args.mode in {"gate-status", "refresh-status"}:
        status = (
            refresh_interface()
            if args.mode == "refresh-status"
            else {
                "state": "BLOCKED_LIVE_GATE",
                "real_capabilities": "NOT_AUTHORIZED",
            }
        )
        print(json.dumps(status, sort_keys=True))
        return 0 if args.mode == "refresh-status" else 3
    try:
        isolated()
        restrict_python_network()
        os.umask(0o077)
        root = Path.cwd()
        check_root(root)
        if not re.fullmatch(r"qa-[a-z0-9-]{1,35}", args.run_id):
            raise Blocked("INVALID_QA_RUN_ID")
        with exclusive(root / ".h3-worker.lock"):
            state = root / args.run_id
            if args.mode == "demo":
                state.mkdir(mode=0o700)
                (state / "hermes").mkdir(mode=0o700)
                (state / "hermes/config.yaml").write_text(CONFIG, encoding="utf-8")
            private_directory(state)
            private_directory(state / "hermes")
            for name in (
                "HOME",
                "XDG_CACHE_HOME",
                "XDG_CONFIG_HOME",
                "XDG_DATA_HOME",
                "XDG_STATE_HOME",
                "TMPDIR",
            ):
                path = os.environ.get(name)
                if not path or not Path(path).resolve().is_relative_to(root):
                    raise Blocked("UNSANITIZED_OFFLINE_ENVIRONMENT")
            if os.environ.get("HERMES_HOME") != str(state / "hermes"):
                raise Blocked("UNSANITIZED_HERMES_HOME")
            allowed_env = {
                "HOME",
                "TMPDIR",
                "XDG_CACHE_HOME",
                "XDG_CONFIG_HOME",
                "XDG_DATA_HOME",
                "XDG_STATE_HOME",
                "PATH",
                "LC_ALL",
                "PYTHONDONTWRITEBYTECODE",
                "HERMES_HOME",
                "PYTHONPATH",
            }
            if set(os.environ) - allowed_env:
                raise Blocked("UNEXPECTED_OFFLINE_ENVIRONMENT")
            with working(state):
                ledger = Measurements(state / "measurements.sqlite")
                key = correlate("h3-process", args.run_id, args.mode)
                ledger.record("START", key)
                try:
                    if args.mode == "demo":
                        composition(state, ledger)
                    elif args.mode == "resume":
                        resume(state, ledger)
                    else:
                        rebuild(state)
                finally:
                    ledger.record("STOP", key)
                write_json(state / f"{args.mode}-measurements.json", ledger.rows())
                write_json(state / f"{args.mode}-latency.json", ledger.report())
                if args.mode == "resume":
                    write_json(state / "pi-feedback.json", pi_export())
        print(
            json.dumps({"mode": args.mode, "classification": QA, "live_gate": "BLOCKED_LIVE_GATE"})
        )
        return 0
    except (Blocked, FileExistsError) as exc:
        print(f"OFFLINE_RUN_BLOCKED {exc}", file=sys.stderr)
        return 3
