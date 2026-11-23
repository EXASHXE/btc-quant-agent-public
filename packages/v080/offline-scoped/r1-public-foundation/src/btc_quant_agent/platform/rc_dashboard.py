"""Versioned adapter for the existing local HTML renderer and atomic Source/Shadow publisher."""
from __future__ import annotations

import html
import json
import os
import tempfile
from pathlib import Path

from .core import fingerprint, primitive
from .rc_models import RCDecision, SCHEMA
from .rc_observe import Observation
from .rc_store import fault
from .reporting import document, source_identity, table
from .swing import timestamp

BUNDLE_SCHEMA = "PROGRAM_A_LOCAL_DASHBOARD_V1"


def snapshot(store, *, now_ms):
    timestamp(now_ms)
    store.verify()
    decisions = [d for d in store.decisions() if d.decision_ms <= now_ms]
    episodes = [store.episode(d.episode_id, asof_ms=now_ms) for d in decisions if d.episode_id]
    observations = [o for o in store.observations() if o["asof_ms"] <= now_ms]
    visible_revisions = any(r.bar.revision and r.bar.durable_ms <= now_ms for r in store.receipts())
    value = {"schema_version": BUNDLE_SCHEMA, "decision_schema": SCHEMA, "exposure": "SYNTHETIC",
             "as_of_ms": now_ms, "producer_sha256": source_identity(),
             "account": "ACCOUNT_UNKNOWN/ACCOUNT_VETO", "source_qualified": False,
             "shadow_advisory_qualified": False, "economically_validated": False,
             "decisions": [d.model_dump(mode="json") for d in decisions],
             "episodes": episodes, "observations": observations,
             "source_stops": list(store.stopped()) + (["VISIBLE_REVISION_REQUIRES_REQUALIFICATION"] if visible_revisions else [])}
    value["snapshot_sha256"] = fingerprint(value)
    validate(value)
    return value


def validate(value):
    expected = {"schema_version", "decision_schema", "exposure", "as_of_ms", "producer_sha256",
                "account", "source_qualified", "shadow_advisory_qualified", "economically_validated",
                "decisions", "episodes", "observations", "source_stops", "snapshot_sha256"}
    if (set(value) != expected or value["schema_version"] != BUNDLE_SCHEMA
            or value["decision_schema"] != SCHEMA or value["exposure"] != "SYNTHETIC"
            or value["account"] != "ACCOUNT_UNKNOWN/ACCOUNT_VETO"
            or any(value[k] is not False for k in ("source_qualified", "shadow_advisory_qualified", "economically_validated"))):
        raise ValueError("RC_DASHBOARD_SCHEMA_OR_AUTHORITY_INVALID")
    timestamp(value["as_of_ms"])
    if value["snapshot_sha256"] != fingerprint({k: v for k, v in value.items() if k != "snapshot_sha256"}):
        raise ValueError("RC_DASHBOARD_DIGEST_MISMATCH")
    decisions = [RCDecision.model_validate_json(json.dumps(d)) for d in value["decisions"]]
    if any(d.decision_ms > value["as_of_ms"] for d in decisions):
        raise ValueError("RC_DASHBOARD_FUTURE_DECISION")
    indexed = {d.episode_id: d for d in decisions if d.episode_id}
    if len(indexed) != len(value["episodes"]):
        raise ValueError("RC_DASHBOARD_EPISODE_COVERAGE_MISMATCH")
    for e in value["episodes"]:
        d = indexed[e["anchors"]["id"]]
        if (e["anchors"]["decision"] != d.model_dump(mode="json") or e["updated_ms"] > value["as_of_ms"]
                or e["state"].get("account") != d.account or e["state"].get("actual_fill") is not False):
            raise ValueError("RC_DASHBOARD_EPISODE_BINDING_INVALID")
    for item in value["observations"]:
        o = Observation.model_validate_json(json.dumps(item))
        if o.episode_id not in indexed or o.asof_ms > value["as_of_ms"]:
            raise ValueError("RC_DASHBOARD_OBSERVATION_BINDING_INVALID")
    return decisions


def render(value, *, now_ms):
    decisions = validate(value)
    if now_ms < value["as_of_ms"]:
        raise ValueError("RC_DASHBOARD_DISPLAY_PRECEDES_SNAPSHOT")
    episodes = {e["anchors"]["id"]: e for e in value["episodes"]}
    observations = {o["episode_id"]: o for o in value["observations"]}
    rows, plans = [], []
    for d in decisions:
        o = d.opportunity
        lifecycle = episodes[d.episode_id]["state"]["status"] if d.episode_id else "NO_EPISODE"
        display = lifecycle if o else d.market_state
        if o and now_ms >= o.expires_ms and lifecycle in ("WATCH", "ARMED"):
            display = "EXPIRED"
        elif o and value["source_stops"] and lifecycle in ("WATCH", "ARMED"):
            display = "SOURCE_BLOCKED"
        elif (o and lifecycle in ("WATCH", "ARMED")
              and now_ms // 14400000 * 14400000 > d.trigger_close_ms):
            display = "DATA_UNAVAILABLE"
        rows.append({"Symbol": d.symbol, "Direction": o.direction if o else "NONE",
                     "1D / 4H regime": " / ".join(d.diagnostics.get(i, {}).get("regime", "UNKNOWN") for i in ("1D", "4H")),
                     "Source": d.source_type, "Last completed 4H / 1D (UTC ms)": " / ".join(str(d.diagnostics.get(i, {}).get("last_completed_end_ms", "UNKNOWN")) for i in ("4H", "1D")),
                     "Original market decision": d.market_state, "Lifecycle / display": display,
                     "Signal / review (UTC ms)": f"{d.decision_ms} / {d.scheduled_review_ms}",
                     "Later synthetic observation": observations.get(d.episode_id, {}).get("outcome", "NOT_OBSERVED"),
                     "Account": d.account, "Reasons": "; ".join(d.reasons)})
        if o:
            plans.append({"Symbol": d.symbol, "Entry zone": o.entry_region, "Structural stop": o.buffered_stop,
                          "Fixed targets": o.target_zones, "Planned gross R": round(d.diagnostics["planned_gross_r"], 4),
                          "Modeled after-cost R": round(o.planned_after_cost_r, 4),
                          "Eligible planned geometry": "/".join(f"{r}R" for r in d.eligible_planned_r),
                          "Entry expiry (UTC ms)": o.expires_ms, "Holding hours": o.holding_hours,
                          "Risk": "SIMULATED PER-UNIT GEOMETRY; ACCOUNT SIZE UNKNOWN",
                          "Confidence / gaps": d.confidence + "; " + "; ".join(d.gaps)})
    body = ("<p><strong>Source status: SYNTHETIC fixture. Native source: NATIVE_UNQUALIFIED "
            "(NATIVE_QUALIFIED FALSE); native ingestion is blocked pending independent authority.</strong></p>"
            "<p>Review once or twice daily at 00:00 / 12:00 UTC. Decisions use completed 4H and 1D candles; "
            "1H confirmation is optional. Intraday horizon 4–24h; multi-day 1–5d. "
            "Entry plans expire on their original clock. Account UNKNOWN / VETO.</p>"
            + table(rows) + "<h2>Ex-ante plan · simulated risk</h2>" + table(plans)
            + "<p>Planned R and later price-path conditions are not executable R, fills, actual holdings, "
              "profits, native qualification or economic evidence. No orders or alerts. "
              "A stale or expired plan is not actionable.</p><p>Snapshot SHA256: "
            + html.escape(value["snapshot_sha256"]) + "</p><details><summary>Reasons, gaps and observation evidence</summary><pre>"
            + html.escape(json.dumps(value, indent=2, allow_nan=False)) + "</pre></details>")
    return document("Swing advisory — local snapshot", body,
                    label="SYNTHETIC · OFFLINE SIMULATOR · ACCOUNT UNKNOWN / VETO · NOT ECONOMIC VALIDATION")


def _publish(root, name, text, *, immutable=False):
    """Extracted from accepted Source/Shadow longhorizon_runtime._publish; UTF-8 explicit."""
    root = Path(root)
    target = root / name
    if any(p.is_symlink() for p in (root, *root.parents)) or target.is_symlink():
        raise ValueError("DASHBOARD_SYMLINK_FORBIDDEN")
    if immutable and target.exists():
        raise ValueError("IMMUTABLE_DASHBOARD_ALREADY_EXISTS")
    fd, temporary = tempfile.mkstemp(dir=root, prefix="." + name + ".", suffix=".part")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        if immutable:
            os.link(temporary, target)
        else:
            os.replace(temporary, target)
        if hasattr(os, "O_DIRECTORY"):
            directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return target


def write_snapshot(root, value, *, crash=None):
    validate(value)
    root = Path(root)
    if any(p.is_symlink() for p in (root, *root.parents)):
        raise ValueError("DASHBOARD_SYMLINK_FORBIDDEN")
    root.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(primitive(value), sort_keys=True, indent=2, allow_nan=False) + "\n"
    immutable = root / ("snapshot-" + value["snapshot_sha256"] + ".json")
    if immutable.exists():
        if immutable.read_text(encoding="utf-8") != encoded:
            raise ValueError("IMMUTABLE_SNAPSHOT_CONFLICT")
    else:
        _publish(root, immutable.name, encoded, immutable=True)
    _publish(root, "latest.json", encoded)
    fault(crash, "after_snapshot_json")
    save_dashboard(root, {"model": value, "exposure": value["exposure"]})
    return immutable


def save_dashboard(root, result):
    from .ui import page

    value = result["model"]
    validate(value)
    if result["exposure"] != value["exposure"]:
        raise ValueError("DASHBOARD_EXPOSURE_MISMATCH")
    return _publish(root, "latest.html", page(value, now_ms=value["as_of_ms"]))
