"""Tests for read-only B2 verification, multi-to-many matching, protection assessment, and account overlays."""

from __future__ import annotations

import json
import shutil
import sqlite3
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from quant_personal_account_b3.b2_reader import B2CardRecord, ReadOnlyB2JournalReader
from quant_personal_account_b3.client import (
    ROUTE_ACCOUNT,
    ROUTE_OPEN_ALGO_ORDERS,
    ROUTE_POSITION_RISK,
)
from quant_personal_account_b3.fixtures import DEFAULT_SYNTHETIC_AS_OF_MS
from quant_personal_account_b3.matching import match_episode_to_account
from quant_personal_account_b3.models import (
    SYNTHETIC_BANNER_TEXT,
    AccountB3Error,
    B2IntegrityError,
    raw_sha256,
)
from quant_personal_account_b3.overlay import build_account_overlay
from quant_personal_account_b3.service import load_synthetic_scenario_into_store
from quant_personal_account_b3.storage import PrivateAccountStore


def test_b2_readonly_immutability_and_tamper_detection(
    tmp_path: Path, b2_pullback_long_journal: dict[str, Any]
) -> None:
    src_db = Path(b2_pullback_long_journal["journal_path"])
    before_sha = raw_sha256(src_db.read_bytes())

    view = ReadOnlyB2JournalReader(src_db).load_and_verify()
    assert view.db_file_sha256 == before_sha
    assert len(view.cards) == 2
    assert len(view.episodes) == 1
    assert len(view.events) >= 2
    assert all(c.evidence == "SYNTHETIC_QA_ONLY" for c in view.cards)

    # Confirm the read-only SQLite connection explicitly rejects writes/migrations/UPDATE/DELETE.
    reader = ReadOnlyB2JournalReader(src_db)
    ro_conn = reader._connect_readonly()
    try:
        for sql in (
            "CREATE TABLE illegal_migration (x INT)",
            "UPDATE cards SET structural_state='HACKED'",
            "DELETE FROM events",
            "INSERT INTO identity VALUES ('{}')",
        ):
            with pytest.raises(sqlite3.OperationalError):
                ro_conn.execute(sql)
    finally:
        ro_conn.close()
    assert raw_sha256(src_db.read_bytes()) == before_sha

    # 1. Tampered card payload digest rejected!
    tampered_card_db = tmp_path / "tampered_card.sqlite"
    shutil.copyfile(src_db, tampered_card_db)
    conn = sqlite3.connect(str(tampered_card_db))
    conn.execute("DROP TRIGGER lock_cards_UPDATE")
    conn.execute("UPDATE cards SET payload_sha = '0000000000000000000000000000000000000000000000000000000000000000'")
    conn.commit()
    conn.close()
    with pytest.raises(B2IntegrityError) as e_card:
        ReadOnlyB2JournalReader(tampered_card_db).load_and_verify()
    assert e_card.value.code == "B2_CARD_DIGEST_MISMATCH"

    # 2. Tampered episode payload digest rejected!
    tampered_ep_db = tmp_path / "tampered_ep.sqlite"
    shutil.copyfile(src_db, tampered_ep_db)
    conn = sqlite3.connect(str(tampered_ep_db))
    conn.execute("DROP TRIGGER lock_episodes_UPDATE")
    conn.execute("UPDATE episodes SET payload_sha = 'ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff'")
    conn.commit()
    conn.close()
    with pytest.raises(B2IntegrityError) as e_ep:
        ReadOnlyB2JournalReader(tampered_ep_db).load_and_verify()
    assert e_ep.value.code == "B2_EPISODE_DIGEST_MISMATCH"

    # 3. Tampered event hash chain rejected!
    tampered_ev_db = tmp_path / "tampered_ev.sqlite"
    shutil.copyfile(src_db, tampered_ev_db)
    conn = sqlite3.connect(str(tampered_ev_db))
    conn.execute("DROP TRIGGER lock_events_UPDATE")
    conn.execute("UPDATE events SET sha = '1111111111111111111111111111111111111111111111111111111111111111' WHERE seq = 1")
    conn.commit()
    conn.close()
    with pytest.raises(B2IntegrityError) as e_ev:
        ReadOnlyB2JournalReader(tampered_ev_db).load_and_verify()
    assert e_ev.value.code == "B2_EVENT_CHAIN_TAMPERED"


def test_all_four_matching_states_multi_to_many_and_owner_entered_associations(
    tmp_path: Path, b2_pullback_long_journal: dict[str, Any]
) -> None:
    b2_view = ReadOnlyB2JournalReader(b2_pullback_long_journal["journal_path"]).load_and_verify()
    exec_card = b2_view.get_card(card_id=b2_pullback_long_journal["executable_card"]["card_id"])
    as_of = max(DEFAULT_SYNTHETIC_AS_OF_MS, exec_card.as_of_ms + 80_000)

    # 1. MATCHED (direct clientOrderId / clientAlgoId across multiple entry/exit orders & fills -> 1-to-many).
    snap_matched = load_synthetic_scenario_into_store(
        scenario="partial_fills_multi_leg",
        private_db=tmp_path / "m_matched.sqlite",
        symbol="BTCUSDT",
        episode_id=exec_card.episode_id,
        as_of_venue_ms=as_of,
    )
    res_matched = match_episode_to_account(exec_card, snap_matched)
    assert res_matched.signal_trade_match == "MATCHED"
    assert res_matched.machine_match_status == "MATCHED"
    assert len(res_matched.matched_order_ids) == 4
    assert len(res_matched.matched_trade_ids) == 5

    # 2. PROBABLE_MATCH (single consistent unlabelled order in entry band/window, NO direct ID).
    snap_prob = load_synthetic_scenario_into_store(
        scenario="probable_matching",
        private_db=tmp_path / "m_prob.sqlite",
        symbol="BTCUSDT",
        episode_id=exec_card.episode_id,
        as_of_venue_ms=as_of,
    )
    res_prob = match_episode_to_account(exec_card, snap_prob)
    assert res_prob.signal_trade_match == "PROBABLE_MATCH"
    assert res_prob.machine_match_status == "PROBABLE_MATCH"
    assert res_prob.matched_order_ids == (80001,)

    # 3. AMBIGUOUS (two unlabelled candidate entry orders in same window -> NEVER forced to MATCHED!).
    snap_ambig = load_synthetic_scenario_into_store(
        scenario="ambiguous_matching",
        private_db=tmp_path / "m_ambig.sqlite",
        symbol="BTCUSDT",
        episode_id=exec_card.episode_id,
        as_of_venue_ms=as_of,
    )
    res_ambig = match_episode_to_account(exec_card, snap_ambig)
    assert res_ambig.signal_trade_match == "AMBIGUOUS"
    assert res_ambig.machine_match_status == "AMBIGUOUS"

    # 4. UNMATCHED (no orders matching, AND symbol+time-only with price far outside entry band stays UNMATCHED!).
    snap_unmatched = load_synthetic_scenario_into_store(
        scenario="no_position",
        private_db=tmp_path / "m_unmatched.sqlite",
        symbol="BTCUSDT",
        episode_id=exec_card.episode_id,
        as_of_venue_ms=as_of,
    )
    res_unmatched = match_episode_to_account(exec_card, snap_unmatched)
    assert res_unmatched.signal_trade_match == "UNMATCHED"

    # Symbol + time alone (price far from entry band, e.g. 150.00 vs band 100.40-101.23) MUST NOT confirm match!
    far_order = replace(snap_prob.all_orders[0], price=Decimal("150.00"), avg_price=Decimal("150.00"))
    far_fill = replace(snap_prob.fills[0], price=Decimal("150.00"))
    snap_symbol_time_only = replace(snap_prob, all_orders=(far_order,), fills=(far_fill,))
    res_sym_time = match_episode_to_account(exec_card, snap_symbol_time_only)
    assert res_sym_time.signal_trade_match == "UNMATCHED"
    assert "SYMBOL_AND_TIME_ALONE_INSUFFICIENT_PRICE_OUTSIDE_BAND" in res_sym_time.reason_codes

    # 5. Many-to-one: two distinct LONG episodes sharing the same open position leg!
    assert exec_card.episode_payload is not None
    peer_ep = {**exec_card.episode_payload, "episode_id": "peer_episode_id_1234567890abcdef"}
    peer_card = B2CardRecord(
        card_id="peer_card_id",
        symbol="BTCUSDT",
        as_of_ms=exec_card.as_of_ms + 1000,
        episode_id=peer_ep["episode_id"],
        market_status="EXECUTABLE",
        evidence="SYNTHETIC_QA_ONLY",
        payload_sha256="peer_sha",
        card_payload={**exec_card.card_payload, "card_id": "peer_card_id", "episode_id": peer_ep["episode_id"], "episode": peer_ep},
        episode_payload=peer_ep,
    )
    res_shared = match_episode_to_account(exec_card, snap_prob, peer_cards=(exec_card, peer_card))
    assert peer_ep["episode_id"] in res_shared.shared_position_episode_ids
    # Competing peer episode also claiming same unlabelled order -> AMBIGUOUS!
    assert res_shared.signal_trade_match == "AMBIGUOUS"

    # 6. OWNER_ENTERED manual associations: immutable, auditable, idempotent, conflict-checked, cannot override contradictions!
    store = PrivateAccountStore(tmp_path / "m_prob.sqlite", create=False)
    assert exec_card.episode_id is not None
    valid_link = store.record_manual_association(
        operator_id="owner-link-1",
        b2_episode_id=exec_card.episode_id,
        b2_card_id=exec_card.card_id,
        symbol="BTCUSDT",
        target_type="ORDER",
        target_id="80001",
        owner_reported_venue_ms=as_of,
        note="Owner verified order 80001 belongs to episode.",
    )
    # Exact retry is idempotent.
    retry_link = store.record_manual_association(
        operator_id="owner-link-1",
        b2_episode_id=exec_card.episode_id,
        b2_card_id=exec_card.card_id,
        symbol="BTCUSDT",
        target_type="ORDER",
        target_id="80001",
        owner_reported_venue_ms=as_of,
        note="Owner verified order 80001 belongs to episode.",
    )
    assert retry_link == valid_link
    # Conflicting reuse of same operator_id rejected!
    with pytest.raises(AccountB3Error) as e_conf:
        store.record_manual_association(
            operator_id="owner-link-1",
            b2_episode_id=exec_card.episode_id,
            b2_card_id=exec_card.card_id,
            symbol="BTCUSDT",
            target_type="ORDER",
            target_id="99999",
            owner_reported_venue_ms=as_of,
        )
    assert e_conf.value.code == "MANUAL_ASSOCIATION_IDEMPOTENCY_CONFLICT"

    # Verified OWNER_ENTERED link upgrades PROBABLE_MATCH -> MATCHED while keeping machine_match_status separate!
    res_with_owner = match_episode_to_account(exec_card, snap_prob, manual_associations=(valid_link,))
    assert res_with_owner.machine_match_status == "PROBABLE_MATCH"
    assert res_with_owner.signal_trade_match == "MATCHED"
    assert len(res_with_owner.owner_entered_associations) == 1
    assert res_with_owner.owner_entered_associations[0]["evidence"] == "OWNER_ENTERED"

    # Contradictory OWNER_ENTERED link (wrong symbol or predating episode freeze) CANNOT overwrite exchange evidence!
    backdated_order = replace(snap_prob.all_orders[0], create_time_ms=int(exec_card.episode_payload["frozen_at_ms"]) - 60_000)
    snap_backdated = replace(snap_prob, all_orders=(backdated_order,))
    res_contradict = match_episode_to_account(exec_card, snap_backdated, manual_associations=(valid_link,))
    assert res_contradict.signal_trade_match == "AMBIGUOUS"
    assert any("OWNER_LINK_PREDATES_EPISODE_FREEZE" in c for c in res_contradict.owner_contradictions)


def test_overlay_position_relations_protection_variants_and_public_only_fallback(
    tmp_path: Path, b2_pullback_long_journal: dict[str, Any]
) -> None:
    b2_view = ReadOnlyB2JournalReader(b2_pullback_long_journal["journal_path"]).load_and_verify()
    exec_card = b2_view.get_card(card_id=b2_pullback_long_journal["executable_card"]["card_id"])
    as_of = max(DEFAULT_SYNTHETIC_AS_OF_MS, exec_card.as_of_ms + 80_000)

    expectations = [
        ("no_position", "SYNTHETIC_CONNECTED", "NO_POSITION", "UNKNOWN", "UNMATCHED"),
        ("one_way_protected", "SYNTHETIC_CONNECTED", "SAME_DIRECTION", "PROTECTED", "MATCHED"),
        ("hedge_long_short", "SYNTHETIC_CONNECTED", "MULTIPLE", "PROTECTED", "MATCHED"),
        ("short_opposite", "SYNTHETIC_CONNECTED", "OPPOSITE_DIRECTION", "PROTECTED", "UNMATCHED"),
        ("multiple_position_legs", "SYNTHETIC_CONNECTED", "MULTIPLE", "PARTIAL", "MATCHED"),
        ("ordinary_and_algo_protection", "SYNTHETIC_CONNECTED", "SAME_DIRECTION", "PROTECTED", "MATCHED"),
        ("partial_protection", "SYNTHETIC_CONNECTED", "SAME_DIRECTION", "PARTIAL", "MATCHED"),
        ("no_protection", "SYNTHETIC_CONNECTED", "SAME_DIRECTION", "UNPROTECTED", "MATCHED"),
        ("conflicting_orders", "SYNTHETIC_CONNECTED", "SAME_DIRECTION", "CONFLICTING", "MATCHED"),
        ("stale_endpoint", "STALE", "UNKNOWN", "UNKNOWN", "UNMATCHED"),
        ("partial_missing_algo", "PARTIAL", "SAME_DIRECTION", "UNKNOWN", "UNMATCHED"),
        ("ambiguous_matching", "SYNTHETIC_CONNECTED", "SAME_DIRECTION", "PROTECTED", "AMBIGUOUS"),
        ("probable_matching", "SYNTHETIC_CONNECTED", "SAME_DIRECTION", "PROTECTED", "PROBABLE_MATCH"),
    ]

    for scenario, exp_acc, exp_rel, exp_prot, exp_match in expectations:
        snap = load_synthetic_scenario_into_store(
            scenario=scenario,
            private_db=tmp_path / f"{scenario}.sqlite",
            symbol="BTCUSDT",
            episode_id=exec_card.episode_id,
            as_of_venue_ms=as_of,
        )
        ov = build_account_overlay(card=exec_card, snapshot=snap)
        # B2 market_setup_status MUST NEVER be overwritten by account status!
        assert ov["market_setup_status"] == "EXECUTABLE", scenario
        assert ov["b2_market_evidence"] == "SYNTHETIC_QA_ONLY", scenario
        assert ov["account_context_status"] == exp_acc, scenario
        assert ov["position_relation"] == exp_rel, scenario
        assert ov["protection_status"] == exp_prot, scenario
        assert ov["signal_trade_match"] == exp_match, scenario
        # Hard policy boundaries & synthetic banners.
        assert ov["real_account_connected"] is False, scenario
        assert ov["synthetic_banner"] == SYNTHETIC_BANNER_TEXT, scenario
        assert ov["portfolio_exposure_limits"] == "UNKNOWN", scenario
        assert ov["safe_position_size"] == "UNKNOWN", scenario
        assert ov["liquidation_clearance"] == "UNKNOWN", scenario
        assert ov["human_actionability"]["order_instruction_issued"] is False, scenario

        if scenario == "partial_protection":
            leg = ov["position_context"][0]
            assert Decimal(leg["sl_covered_qty"]) == Decimal("0.400")
            assert Decimal(leg["uncovered_qty"]) == Decimal("0.600")
        if scenario == "ordinary_and_algo_protection":
            leg = ov["position_context"][0]
            assert Decimal(leg["sl_covered_qty"]) == Decimal("0.800")
            assert Decimal(leg["trailing_covered_qty"]) == Decimal("0.200")
            assert Decimal(leg["uncovered_qty"]) == Decimal("0.000")
            assert Decimal(leg["tp_covered_qty"]) == Decimal("0.500")
        if scenario == "partial_missing_algo":
            # openOrders alone without openAlgoOrders MUST NOT mark PROTECTED or UNPROTECTED!
            assert ov["protection_status"] == "UNKNOWN"
            assert any(ROUTE_OPEN_ALGO_ORDERS in r for r in ov["protection_reasons"])
            assert ov["human_actionability"]["exposure_and_tpsl_verified"] is False

    # Omitted positionRisk row WITHOUT zero-margin account corroboration MUST stay UNKNOWN (never fabricated zero!).
    snap_omitted = load_synthetic_scenario_into_store(
        scenario="one_way_protected",
        private_db=tmp_path / "omitted_pos.sqlite",
        symbol="BTCUSDT",
        episode_id=exec_card.episode_id,
        as_of_venue_ms=as_of,
    )
    # Remove BTCUSDT row while account still has non-zero totalPositionInitialMargin ("500.00").
    snap_omitted_only = replace(snap_omitted, positions=())
    ov_omitted = build_account_overlay(card=exec_card, snapshot=snap_omitted_only)
    assert ov_omitted["position_relation"] == "UNKNOWN"
    assert "POSITION_ROW_OMITTED_NOT_PROOF_OF_ZERO_POSITION" in ov_omitted["position_relation_reasons"]
    assert ov_omitted["protection_status"] == "UNKNOWN"

    # Public-only fallback (snapshot=None): B2 market status continues completely unchanged!
    ov_fallback = build_account_overlay(card=exec_card, snapshot=None)
    assert ov_fallback["market_setup_status"] == "EXECUTABLE"
    assert ov_fallback["account_context_status"] == "UNAVAILABLE"
    assert ov_fallback["position_relation"] == "UNKNOWN"
    assert ov_fallback["protection_status"] == "UNKNOWN"
    assert ov_fallback["signal_trade_match"] == "UNMATCHED"
    assert ov_fallback["human_actionability"]["exposure_and_tpsl_verified"] is False
    assert ov_fallback["portfolio_context"]["wallet_balance"] == "UNKNOWN"
    assert ov_fallback["b2_original_account_fields"]["account_context_status"] == "UNAVAILABLE"
    assert ROUTE_ACCOUNT not in ov_fallback["endpoint_coverage"]
    assert ROUTE_POSITION_RISK not in ov_fallback["endpoint_coverage"]
    # Verify full overlay JSON serializes deterministically with zero float NaN issues.
    assert json.loads(json.dumps(ov_fallback))["overlay_id"] == ov_fallback["overlay_id"]
