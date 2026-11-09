"""Finite deterministic manual workflows, never current market signals."""

import json

from ..rc_fixture import TRIGGER
from .fixtures import dataset
from .source import Source
from .product import Product


def run(output, scenario="positive", grace_ms=120000):
    source = Source(output, create=True, synthetic=True, grace_ms=grace_ms)
    kind = "flat" if scenario == "all-no-setup" else "mixed"
    data = dataset(kind)
    (source.directory / "dataset.json").write_text(data.model_dump_json(indent=2) + "\n")
    source.ingest(data)
    if scenario == "clock-blocked":
        try:
            source.ingest(dataset("irreconcilable"))
        except ValueError as exc:
            source.events.append("DEMO_EXPECTED_BLOCK", {"reason": str(exc)})
    source.tick(TRIGGER + grace_ms, 1760 if scenario in ("clock-reconciled", "clock-blocked") else 0)
    blocked = None
    if scenario == "clock-reconciled":
        blocked = source.assess()
        witness = dataset(kind, source_ms=TRIGGER + grace_ms, origin="INDEPENDENT_DETERMINISTIC_REPLAY")
        (source.directory / "witness.json").write_text(witness.model_dump_json(indent=2) + "\n")
        source.reconcile(witness)
    product = Product(source)
    decisions = [product.review(s) for s in ("BTCUSDT", "ETHUSDT", "SOLUSDT")]
    dashboard = product.dashboard()
    result = {
        "mode": "EXPLORATORY_MVP",
        "evidence_class": source.meta["evidence_class"],
        "scenario": scenario,
        "states": [d.market_state if hasattr(d, "market_state") else d["status"] for d in decisions],
        "clock_hold_before_reconciliation": {k: v for k, v in blocked.items() if k != "records"}
        if blocked
        else None,
        **dashboard,
        "source_qualified": False,
        "native_requests": 0,
    }
    if product.decisions():
        result["evaluation"] = product.evaluate(source.directory / "evaluation_initial")
    (source.directory / "demo_receipt.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def followup(source):
    if not source.synthetic:
        raise ValueError("SYNTHETIC_FOLLOWUP_FORBIDDEN_ON_AUTHORIZED_IMPORT")
    p = Product(source)
    decision = next(d for d in p.decisions() if d.opportunity)
    original = decision.model_dump(mode="json")
    future = dataset("future:target", source_ms=TRIGGER + 50 * 3600000 + 1000, decision=decision)
    source.tick(future.reference.lower_ms)
    source.ingest(future)
    observation = p.observe(decision.episode_id)
    restarted = Product(Source(source.directory))
    assert (
        next(d for d in restarted.decisions() if d.episode_id == decision.episode_id).model_dump(mode="json")
        == original
    )
    return {
        "observation": observation,
        "restart_original_plan_unchanged": True,
        "episode": restarted.episode(decision.episode_id),
        **p.dashboard(),
        "evaluation": p.evaluate(source.directory / "evaluation_later"),
    }
