"""Family F tests: default-deny live capability gate, dual-approval binding, B3 isolation & preservation."""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

import pytest
from quant_hermes_feishu_h1.contract import ContractError
from quant_hermes_feishu_h1.journal_reader import ApprovedJournalRegistry, ApprovedJournalSource

from quant_hermes_feishu_h2b.activation_gate import (
    CONTROLLER_SIGN_DOMAIN,
    ENROLLMENT_LINE_PREFIX,
    HAS_ED25519,
    OWNER_SIGN_DOMAIN,
    PRODUCTION_TRUST_ROOT,
    GateDenialError,
    H2BActivationGate,
    H2BActivationGrant,
    H2BApprovalClaim,
    H2BRevocationStore,
    H2BTrustRoot,
    reject_consumer_subscription_entitlement,
)
from quant_hermes_feishu_h2b.cli import run_offline_demo
from quant_hermes_feishu_h2b.constants import (
    ACCEPTED_H1_WHEEL_SHA256,
    LIVE_CAPABILITY_EXIT_CODE,
    LIVE_FEISHU_ERROR,
    LIVE_MODEL_ERROR,
)

H2B_ROOT = Path(__file__).resolve().parents[1]
WORKSPACES = H2B_ROOT.parent
B3_JOURNAL = WORKSPACES / "lt-v080-personal-mvp-account-aware-b3-01/evidence/demo/decision_with_account.sqlite"
B5_JOURNAL = WORKSPACES / "lt-v080-personal-mvp-live-public-b5-01/evidence/replay-input/journal.sqlite"
B2_DEMO = WORKSPACES / "lt-v080-sol62-personal-mvp-market-decision-b2-01/evidence/demo"


def test_f1_production_trust_root_default_deny_cannot_be_bypassed_by_env_or_cli(monkeypatch, tmp_path):
    monkeypatch.setenv("QUANT_H2B_ALLOW_LIVE", "1")
    monkeypatch.setenv("QUANT_H2B_BYPASS_GATE", "true")
    monkeypatch.setenv("FEISHU_APP_ID", "cli_fake")
    monkeypatch.setenv("FEISHU_APP_SECRET", "fake_secret")

    gate = H2BActivationGate(trust_root=PRODUCTION_TRUST_ROOT)
    for cap, expected_code in (
        ("FEISHU_OUTBOUND_DM_ONCE", LIVE_FEISHU_ERROR),
        ("FEISHU_INBOUND_DM_BOUNDED", LIVE_FEISHU_ERROR),
        ("MODEL_EXPLANATION_OPTIONAL", LIVE_MODEL_ERROR),
        ("FEISHU_PERSISTENT_GATEWAY_AND_RECURRING", LIVE_FEISHU_ERROR),
    ):
        with pytest.raises(GateDenialError) as exc:
            gate.authorize_capability(
                cap,
                app_id="cli_fake",
                tenant_key="tenant_fake",
                recipient_open_id="ou_owner001",
                chat_id="oc_dmowner001",
                sender_id="hermes-h2b-sole-sender",
                outbox_path=tmp_path / "ob.sqlite",
                model_auth_scope="API_KEY" if cap == "MODEL_EXPLANATION_OPTIONAL" else "NONE",
            )
        assert exc.value.code == expected_code

    for target, expected_out in (
        ("feishu-live", LIVE_FEISHU_ERROR),
        ("model-oauth", LIVE_MODEL_ERROR),
    ):
        proc = subprocess.run(
            [sys.executable, "-m", "quant_hermes_feishu_h2b", "check-live-gate", "--target", target, "--ignore-env-bypass"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == LIVE_CAPABILITY_EXIT_CODE
        assert proc.stdout.strip() == expected_out

    for claim in ("chatgpt_plus", "chatgpt_pro", "google_ai_pro"):
        with pytest.raises(GateDenialError) as exc_sub:
            reject_consumer_subscription_entitlement(claim)
        assert exc_sub.value.code == LIVE_MODEL_ERROR


def test_f2_bounded_oneshot_grant_binding_expiry_revocation_kill_switch_and_ed25519(tmp_path):
    import os

    anchor = tmp_path / "private/h2b_anchor"
    anchor.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(anchor.parent, 0o700)
    anchor.write_text(f"{ENROLLMENT_LINE_PREFIX}run-smoke-001\n", encoding="utf-8")
    os.chmod(anchor, 0o600)
    anchor_sha = hashlib.sha256(anchor.read_bytes()).hexdigest()

    outbox_path = (tmp_path / "state/h1_outbox.sqlite").resolve()
    rev_path = (tmp_path / "state/revocations.sqlite").resolve()
    kill_path = (tmp_path / "state/kill_switch.json").resolve()
    rel_sha = "1" * 64

    claim = H2BApprovalClaim(
        capability="FEISHU_OUTBOUND_DM_ONCE",
        run_id="smoke-run-01",
        release_wheel_sha256=rel_sha,
        h1_wheel_sha256=ACCEPTED_H1_WHEEL_SHA256,
        app_id="cli_h2boffline001",
        tenant_key="tenant_h2b_001",
        owner_open_id="ou_owner001",
        authorized_dm_chat_id="oc_dmowner001",
        runtime_uid=os.getuid(),
        sender_id="hermes-h2b-sole-sender",
        outbox_db_path=str(outbox_path),
        model_auth_scope="NONE",
        not_before_ms=1000,
        expires_ms=2000,
        max_outbound_messages=1,
        max_inbound_turns=0,
        single_smoke_test_only=True,
    )
    claim_sha = claim.digest_sha256()

    trust_root = H2BTrustRoot(
        live_enabled=True,
        release_wheel_sha256=rel_sha,
        h1_wheel_sha256=ACCEPTED_H1_WHEEL_SHA256,
        app_id="cli_h2boffline001",
        tenant_key="tenant_h2b_001",
        owner_open_id="ou_owner001",
        authorized_dm_chat_id="oc_dmowner001",
        runtime_uid=os.getuid(),
        sender_id="hermes-h2b-sole-sender",
        outbox_db_path=str(outbox_path),
        revocation_db_path=str(rev_path),
        kill_switch_path=str(kill_path),
        enrollment_anchor_path=str(anchor),
        enrollment_anchor_sha256=anchor_sha,
        require_ed25519_signatures=False,
        allowed_capabilities=frozenset({"FEISHU_OUTBOUND_DM_ONCE"}),
    )
    rev_store = H2BRevocationStore(rev_path, kill_switch_path=kill_path)
    gate = H2BActivationGate(
        trust_root=trust_root,
        grant=H2BActivationGrant(claim=claim, owner_claim_sha256=claim_sha, controller_claim_sha256=claim_sha),
        revocation_store=rev_store,
        observed_release_wheel_sha256=rel_sha,
        observed_h1_wheel_sha256=ACCEPTED_H1_WHEEL_SHA256,
    )

    # First smoke test within bounds passes once
    res1 = gate.authorize_capability(
        "FEISHU_OUTBOUND_DM_ONCE",
        app_id="cli_h2boffline001",
        tenant_key="tenant_h2b_001",
        recipient_open_id="ou_owner001",
        chat_id="oc_dmowner001",
        sender_id="hermes-h2b-sole-sender",
        outbox_path=outbox_path,
        now_ms=1500,
        consume_quota=True,
    )
    assert res1["authorized"] is True and res1["quota_used"] == 1

    # Second send with same smoke grant is DENIED (no recurring access)
    with pytest.raises(GateDenialError):
        gate.authorize_capability(
            "FEISHU_OUTBOUND_DM_ONCE",
            app_id="cli_h2boffline001",
            tenant_key="tenant_h2b_001",
            recipient_open_id="ou_owner001",
            chat_id="oc_dmowner001",
            sender_id="hermes-h2b-sole-sender",
            outbox_path=outbox_path,
            now_ms=1501,
            consume_quota=True,
        )

    # Mismatches & expiry & revocation & kill-switch fail closed
    for kw in (
        {"app_id": "cli_other999"},
        {"tenant_key": "tenant_other"},
        {"recipient_open_id": "ou_other"},
        {"chat_id": "oc_other"},
        {"sender_id": "second-sender"},
        {"now_ms": 2500},
    ):
        call_kw = {
            "app_id": "cli_h2boffline001",
            "tenant_key": "tenant_h2b_001",
            "recipient_open_id": "ou_owner001",
            "chat_id": "oc_dmowner001",
            "sender_id": "hermes-h2b-sole-sender",
            "outbox_path": outbox_path,
            "now_ms": 1500,
            **kw,
        }
        with pytest.raises(GateDenialError):
            gate.authorize_capability("FEISHU_OUTBOUND_DM_ONCE", **call_kw)  # type: ignore[arg-type]

    # Kill switch stops future usage immediately
    rev_store.write_kill_switch(reason="owner_emergency_stop", ts_ms=1550)
    with pytest.raises(GateDenialError):
        gate.authorize_capability(
            "FEISHU_OUTBOUND_DM_ONCE",
            app_id="cli_h2boffline001",
            tenant_key="tenant_h2b_001",
            recipient_open_id="ou_owner001",
            chat_id="oc_dmowner001",
            sender_id="hermes-h2b-sole-sender",
            outbox_path=outbox_path,
            now_ms=1555,
        )

    # Full Ed25519 distinct Owner + Controller dual-signature check when cryptography is installed (Mixed venv)
    if HAS_ED25519:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

        ed_rev = H2BRevocationStore(tmp_path / "state/ed_revocations.sqlite")
        ed_claim = H2BApprovalClaim(
            capability="FEISHU_OUTBOUND_DM_ONCE",
            run_id="smoke-ed-01",
            release_wheel_sha256=rel_sha,
            h1_wheel_sha256=ACCEPTED_H1_WHEEL_SHA256,
            app_id="cli_h2boffline001",
            tenant_key="tenant_h2b_001",
            owner_open_id="ou_owner001",
            authorized_dm_chat_id="oc_dmowner001",
            runtime_uid=os.getuid(),
            sender_id="hermes-h2b-sole-sender",
            outbox_db_path=str(outbox_path),
            model_auth_scope="NONE",
            not_before_ms=1000,
            expires_ms=2000,
            max_outbound_messages=1,
            max_inbound_turns=0,
            single_smoke_test_only=True,
        )
        owner_priv = Ed25519PrivateKey.generate()
        ctrl_priv = Ed25519PrivateKey.generate()
        owner_pub_hex = owner_priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()
        ctrl_pub_hex = ctrl_priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()
        ed_sha = ed_claim.digest_sha256()
        ed_grant = H2BActivationGrant(
            claim=ed_claim,
            owner_approval_hex=owner_priv.sign(f"{OWNER_SIGN_DOMAIN}{ed_sha}".encode("ascii")).hex(),
            controller_approval_hex=ctrl_priv.sign(f"{CONTROLLER_SIGN_DOMAIN}{ed_sha}".encode("ascii")).hex(),
        )
        ed_root = H2BTrustRoot(
            live_enabled=True,
            release_wheel_sha256=rel_sha,
            h1_wheel_sha256=ACCEPTED_H1_WHEEL_SHA256,
            app_id="cli_h2boffline001",
            tenant_key="tenant_h2b_001",
            owner_open_id="ou_owner001",
            authorized_dm_chat_id="oc_dmowner001",
            runtime_uid=os.getuid(),
            sender_id="hermes-h2b-sole-sender",
            outbox_db_path=str(outbox_path),
            revocation_db_path=str(tmp_path / "state/ed_revocations.sqlite"),
            enrollment_anchor_path=str(anchor),
            enrollment_anchor_sha256=anchor_sha,
            owner_ed25519_public_hex=owner_pub_hex,
            controller_ed25519_public_hex=ctrl_pub_hex,
            require_ed25519_signatures=True,
            allowed_capabilities=frozenset({"FEISHU_OUTBOUND_DM_ONCE"}),
        )
        ed_gate = H2BActivationGate(
            trust_root=ed_root,
            grant=ed_grant,
            revocation_store=ed_rev,
            observed_release_wheel_sha256=rel_sha,
            observed_h1_wheel_sha256=ACCEPTED_H1_WHEEL_SHA256,
        )
        ed_res = ed_gate.authorize_capability(
            "FEISHU_OUTBOUND_DM_ONCE",
            app_id="cli_h2boffline001",
            tenant_key="tenant_h2b_001",
            recipient_open_id="ou_owner001",
            chat_id="oc_dmowner001",
            sender_id="hermes-h2b-sole-sender",
            outbox_path=outbox_path,
            now_ms=1500,
            consume_quota=True,
        )
        assert ed_res["authorized"] is True

        # Reject corrupted signature
        bad_gate = H2BActivationGate(
            trust_root=ed_root,
            grant=H2BActivationGrant(
                claim=ed_claim,
                owner_approval_hex=ed_grant.owner_approval_hex,
                controller_approval_hex="00" * 64,
            ),
            revocation_store=ed_rev,
            observed_release_wheel_sha256=rel_sha,
            observed_h1_wheel_sha256=ACCEPTED_H1_WHEEL_SHA256,
        )
        with pytest.raises(GateDenialError):
            bad_gate.authorize_capability(
                "FEISHU_OUTBOUND_DM_ONCE",
                app_id="cli_h2boffline001",
                tenant_key="tenant_h2b_001",
                recipient_open_id="ou_owner001",
                chat_id="oc_dmowner001",
                sender_id="hermes-h2b-sole-sender",
                outbox_path=outbox_path,
                now_ms=1500,
            )


def test_f3_b3_private_isolation_offline_demo_and_baseline_preservation(tmp_path):
    # B3 database is rejected and never imported
    with pytest.raises(ContractError) as exc_b3:
        ApprovedJournalRegistry([ApprovedJournalSource("b3_leak", B3_JOURNAL)])
    assert exc_b3.value.code == "UNAUTHORIZED"
    assert "b3" in exc_b3.value.message.lower() or "private" in exc_b3.value.message.lower()

    demo_out = tmp_path / "demo_out"
    summary = run_offline_demo(
        journal_specs=[
            ("b5_pl", B5_JOURNAL),
            ("b2_es", B2_DEMO / "early-short/decision.sqlite"),
        ],
        output_dir=demo_out,
    )
    assert summary["real_feishu_delivery_measured"] is False
    assert summary["real_model_api_used"] is False
    assert summary["request_reprice_human"]["error"]["code"] == "REPRICE_NOT_AUTHORIZED"
    assert (demo_out / "summary.json").exists()
    assert (demo_out / "outbound_ledger.json").exists()
    assert (demo_out / "inbound_transcripts.json").exists()

    proc = subprocess.run([sys.executable, str(H2B_ROOT / "tools/preserve.py")], capture_output=True, text=True, check=True)
    assert "PASS v0.8.0" in proc.stdout
    assert "lt-v080-gemini-neon-hermes-h1-p0-interop-fix-01 (71 sealed files)" in proc.stdout
    assert "lt-v080-sol62-h2a-b5-phaseb-activation-01 (69 sealed files)" in proc.stdout
    assert "Program J (323 files)" in proc.stdout
