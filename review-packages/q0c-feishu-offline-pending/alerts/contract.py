"""Versioned schema plus conservative offline admission, using stdlib only."""

import json
import math
from pathlib import Path
from urllib.parse import urlsplit

SCHEMA = json.loads((Path(__file__).resolve().parent.parent /
                     "Q0C_EVENT_CONTRACT.json").read_text(encoding="utf-8"))
TERMINAL = {"INVALIDATED", "EXPIRED"}
PRIORITY = {"INVALIDATED": 0, "EXPIRED": 0, "ENTRY_READY": 1,
            "SYSTEM_DEGRADED": 2, "SETUP_READY": 3, "WATCH": 4}


def _check(value, schema, path="event"):
    if "$ref" in schema:
        return _check(value, SCHEMA["$defs"][schema["$ref"].split("/")[-1]], path)
    if "oneOf" in schema:
        matches = 0
        for variant in schema["oneOf"]:
            try:
                _check(value, variant, path)
                matches += 1
            except ValueError:
                pass
        if matches != 1:
            raise ValueError(path + ": does not match exactly one event schema")
        return
    kind = schema.get("type")
    valid = {"object": lambda: type(value) is dict,
             "array": lambda: type(value) is list,
             "string": lambda: type(value) is str,
             "boolean": lambda: type(value) is bool,
             "number": lambda: type(value) in (int, float) and math.isfinite(value)}
    if kind and not valid[kind]():
        raise ValueError(path + ": invalid type")
    if "const" in schema and (type(value) is not type(schema["const"]) or value != schema["const"]):
        raise ValueError(path + ": invalid constant")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(path + ": invalid enum")
    if kind == "object":
        if set(schema["required"]) - value.keys() or value.keys() - schema["properties"].keys():
            raise ValueError(path + ": missing or unknown fields")
        for key, child in value.items():
            _check(child, schema["properties"][key], path + "." + key)
    elif kind in ("string", "array"):
        low, high = ("minLength", "maxLength") if kind == "string" else ("minItems", "maxItems")
        if not schema.get(low, 0) <= len(value) <= schema.get(high, float("inf")):
            raise ValueError(path + ": invalid length")
        if kind == "array":
            for item in value:
                _check(item, schema["items"], path + "[]")
    elif kind == "number":
        if value < schema.get("minimum", -float("inf")) or value > schema.get("maximum", float("inf")):
            raise ValueError(path + ": out of range")
        if "exclusiveMinimum" in schema and value <= schema["exclusiveMinimum"]:
            raise ValueError(path + ": out of range")


def validate_shape(event):
    _check(event, SCHEMA)


def after_cost_r(event, entry):
    plan = event["plan"]
    direction = 1 if event["side"] == "LONG" else -1
    cost = entry * (plan["model"]["fee_bps_round_trip"] +
                    plan["model"]["slippage_bps_round_trip"]) / 10000
    reward = sum(tp["weight"] * direction * (tp["price"] - entry)
                 for tp in plan["take_profits"])
    return (reward - cost) / (abs(entry - plan["hard_stop"]) + cost)


def admit(event, now, policy):
    validate_shape(event)
    if not event["watermark"]["synthetic"] or not event["watermark"]["test"]:
        raise ValueError("offline_only_requires_synthetic_test")
    kind = event["event_type"]
    if event["account_status"] == "VETO" and kind in {"ENTRY_READY", "WATCH", "SETUP_READY"}:
        raise ValueError("account_veto")
    link = urlsplit(event["dashboard_url"])
    if link.scheme != "https" or not link.hostname or link.username or link.password or link.query or link.fragment:
        raise ValueError("dashboard_requires_https_without_credentials_query_fragment")
    if not event["eligible_at"] <= now < event["expires_at"]:
        raise ValueError("event_not_eligible_or_expired")
    if now - event["eligible_at"] > policy.max_signal_age:
        raise ValueError("stale_signal")
    source = event["source"]
    if not source["trusted"] or not source["admitted"] or source["quality"] == "REJECTED":
        raise ValueError("source_not_admitted")
    if not source["observed_at"] <= source["received_at"] <= now:
        raise ValueError("source_time_order")
    if now - source["observed_at"] > policy.max_source_age:
        raise ValueError("source_stale")
    if kind == "SYSTEM_DEGRADED":
        return
    if kind in TERMINAL:
        if kind == "INVALIDATED" and not event["invalidation"]["triggered"]:
            raise ValueError("invalidation_not_triggered")
        if kind == "EXPIRED" and event["candidate_expires_at"] > now:
            raise ValueError("candidate_not_expired")
        return  # historical plan/quote must not prevent fresh terminal notifications
    if source["quality"] != "GOOD" or not event["regime_4h"]["admitted"]:
        raise ValueError("data_or_regime_gate")
    if event["invalidation"]["triggered"] or event["candidate_expires_at"] <= now:
        raise ValueError("candidate_terminal")
    for key, duration in (("setup_1h", 3600), ("confirmation_15m", 900)):
        bar = event[key]
        if bar["closed_at"] > source["observed_at"]:
            raise ValueError("future_bar")
        required = kind == "ENTRY_READY" or (kind == "SETUP_READY" and key == "setup_1h")
        if required and (not bar["completed"] or not bar["valid"] or now - bar["closed_at"] > duration):
            raise ValueError("uncompleted_invalid_or_stale_bar")
    quote, plan = event["quote"], event["plan"]
    if not all(quote[k] for k in ("trusted", "current", "gate_passed", "path_admitted")):
        raise ValueError("quote_price_path_gate")
    if not quote["as_of"] <= quote["received_at"] <= now or now - quote["as_of"] > policy.max_quote_age:
        raise ValueError("quote_stale_or_future")
    low, high = plan["entry_area"]
    if low > high or not low <= quote["price"] <= high or not low <= plan["model"]["entry_reference"] <= high:
        raise ValueError("entry_area_gate")
    targets = [tp["price"] for tp in plan["take_profits"]]
    long = event["side"] == "LONG"
    if (long and (plan["hard_stop"] >= low or min(targets) <= high or targets != sorted(set(targets)))) or (
            not long and (plan["hard_stop"] <= high or max(targets) >= low or targets != sorted(set(targets), reverse=True))):
        raise ValueError("stop_or_tp_direction")
    if abs(sum(tp["weight"] for tp in plan["take_profits"]) - 1) > 1e-9:
        raise ValueError("tp_weights_must_sum_to_one")
    floor = plan["model"]["min_after_cost_r"]
    if not floor <= plan["after_cost_r"] <= after_cost_r(event, plan["model"]["entry_reference"]) + 1e-9:
        raise ValueError("planned_after_cost_r_gate")
    if after_cost_r(event, quote["price"]) < floor:
        raise ValueError("current_after_cost_r_gate")
    if kind == "ENTRY_READY":
        delay = event["human_delay"]
        if not delay["feasible"] or not delay["assessed_at"] <= now or now - delay["assessed_at"] > policy.max_source_age:
            raise ValueError("human_delay_assessment")
        if min(delay["valid_until"], event["candidate_expires_at"]) < now + 600:
            raise ValueError("human_delay_horizon")
        entries = [quote["price"], delay["worst_entry_at_5m"], delay["worst_entry_at_10m"]]
        if entries != sorted(entries, reverse=not long):
            raise ValueError("human_delay_entries_must_be_directionally_conservative")
        for suffix in ("5m", "10m"):
            entry = delay["worst_entry_at_" + suffix]
            reported = delay["after_cost_r_at_" + suffix]
            if not low <= entry <= high or not floor <= reported <= after_cost_r(event, entry) + 1e-9:
                raise ValueError("human_delay_price_or_after_cost_r_gate")
