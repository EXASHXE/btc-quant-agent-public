"""H2-A-only tests. Signing keys and market inputs in this file are synthetic."""

import os
from dataclasses import replace
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from quant_personal_decision_b2.model import DecisionError
from quant_personal_public_b1.fixture import FixtureClock, fixture_reply
from quant_personal_public_b1.policy import SourceBlocked
from quant_personal_public_b1.session import RunIdentity
from quant_personal_public_b1.store import sha
from quant_personal_public_bridge_b4.routes import DEPTH, INSTRUMENTS, TIME

from quant_personal_live_public_b5.admission import Adapter
from quant_personal_live_public_b5.approval import _signed, verify_envelope
from quant_personal_live_public_b5.collection import collect
from quant_personal_live_public_b5.contract import (
    APPROVAL_SCHEMA, AUTHORITY, CONTRACT, GENUINE, INTERVALS, QA, ROUTES, SYMBOL_ORDER, TASK, RouteRequest, digest,
)
from quant_personal_live_public_b5.decision import engine
from quant_personal_live_public_b5.enrollment import ANCHOR_PREFIX, Enrollment, enroll_once, require_enrolled
from quant_personal_live_public_b5.ledger import Active, Ledger, secure_storage
from quant_personal_live_public_b5.offline import FixtureWire
from quant_personal_live_public_b5.planning import preview
from quant_personal_live_public_b5.stages import SCOPE_V2, STAGE_CONTRACT, TIMEOUT_PROFILE
from quant_personal_live_public_b5.trust import TrustRoots


class LocalTest(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.state=self.root/"market.sqlite"
        self.clock=FixtureClock()
        self.now=self.clock.sample().wall_ms
        self.owner=Ed25519PrivateKey.from_private_bytes(bytes([13])*32)
        self.controller=Ed25519PrivateKey.from_private_bytes(bytes([17])*32)
        self.roots=TrustRoots(self.owner.public_key().public_bytes_raw(),
                              self.controller.public_key().public_bytes_raw(), self.state,
                              "1"*64, os.geteuid(),"2"*64)

    def scope(self, market=False):
        total={"count":39,"weight":42} if market else {"count":2,"weight":2}
        return {"schema":SCOPE_V2,"task":TASK,"endpoint_contract":CONTRACT,"host":AUTHORITY,
                "methods":["GET"],"routes":list(ROUTES),"symbols":list(SYMBOL_ORDER),"frames":list(INTERVALS),
                "network":{"region":"XX","egress_id":self.roots.egress_id,"netns_inode":1,"interface":"qa-absent",
                           "source_ipv4":"192.0.2.1","resolver_ipv4":"192.0.2.2","approved_ipv4":["1.1.1.1"],
                           "route_table_sha256":"3"*64,"direct_only":True},
                "storage":{"ledger":str(self.state),"journal":str(self.root/"journal.sqlite"),
                           "retention_days":7,"owner_local_only":True},
                "budget":{"bootstrap":dict(total),"refresh_5":None,"refresh_10":None,"total":dict(total),
                          "rolling_60s":{"count":96,"weight":120},"headroom_weight":5},
                "funding":{"documented_numeric_ip_weight":1 if market else None,
                           "official_evidence_sha256":"4"*64 if market else None},
                "activation_plan":{"contract":STAGE_CONTRACT,"canary":{"count":2,"weight":2},
                                   "market":{"count":37,"weight":40} if market else None,
                                   "timeout_profile":TIMEOUT_PROFILE},"live_permitted":True}

    def envelope(self, scope):
        claims={"task":TASK,"scope_sha256":digest(scope),"release_sha256":"5"*64,
                "egress_id":self.roots.egress_id,"run_id":"6"*32,
                "not_before_ms":self.now-1_000,"expires_ms":self.now+60_000}
        return {"schema":APPROVAL_SCHEMA,"claims":claims,
                "owner_signature":self.owner.sign(_signed("owner",claims)).hex(),
                "controller_signature":self.controller.sign(_signed("controller",claims)).hex()}

    def approve(self, scope, envelope=None, *, at=None, release="5"*64):
        return verify_envelope(envelope or self.envelope(scope),scope,self.roots,
                               release,self.now if at is None else at)

    def active(self, market=False, *, scope=None):
        approval=self.approve(scope if scope is not None else self.scope(market))
        active=Active(Ledger.qa(self.state,approval), approval,self.clock,RunIdentity("H2A-QA-BOOT","H2A-QA-SESSION"))
        active.claim()
        return active

    def enrollment(self):
        marker=self.root/"anchor"
        body=ANCHOR_PREFIX+bytes([11]).hex().encode()*32+b"\n"
        fd=os.open(marker,os.O_WRONLY | os.O_CREAT | os.O_EXCL,0o600)
        with os.fdopen(fd,"wb") as output:
            output.write(body)
        meta=marker.stat()
        return Enrollment(marker,meta.st_dev,meta.st_ino,sha(body)),body

    def create_registry(self):
        descriptor=os.open(self.state,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        os.close(descriptor)
        return "REGISTERED"


class ApprovalTests(LocalTest):
    def test_stage2_is_covered_by_exact_dual_signature(self):
        initial=self.scope()
        canary=self.approve(initial)
        market=self.scope(True)
        self.assertFalse(canary.scope.stage_plan.market_allowed)
        self.assertTrue(self.approve(market).scope.stage_plan.market_allowed)
        with self.assertRaisesRegex(SourceBlocked,"ACTIVATION_BINDING_MISMATCH"):
            self.approve(market,self.envelope(initial))
        altered=self.envelope(market)
        altered["controller_signature"]="1"*128
        with self.assertRaisesRegex(SourceBlocked,"ACTIVATION_SIGNATURE_INVALID"):
            self.approve(market,altered)
        with self.assertRaisesRegex(SourceBlocked,"ACTIVATION_BINDING_MISMATCH"):
            self.approve(market,release="7"*64)
        with self.assertRaisesRegex(SourceBlocked,"ACTIVATION_EXPIRED_OR_EARLY"):
            self.approve(market,at=self.now+60_000)

    def test_unresolved_funding_blocks_stage2_and_excess_scope(self):
        market=self.scope(True)
        market["funding"]={"documented_numeric_ip_weight":None,"official_evidence_sha256":None}
        with self.assertRaisesRegex(SourceBlocked,"FUNDING_WEIGHT_UNRESOLVED"):
            self.approve(market)
        market=self.scope(True)
        market["activation_plan"]["market"]["weight"]=39
        with self.assertRaisesRegex(SourceBlocked,"MARKET_STAGE_BUDGET_INVALID"):
            self.approve(market)
        market=self.scope(True)
        market["budget"]["total"]["weight"]+=1
        market["budget"]["bootstrap"]["weight"]+=1
        with self.assertRaisesRegex(SourceBlocked,"STAGE_TOTAL_BUDGET_MISMATCH"):
            self.approve(market)
        market=self.scope(True)
        market["budget"]["refresh_5"]={"count":17,"weight":30}
        with self.assertRaisesRegex(SourceBlocked,"TIMED_REFRESH_DISABLED"):
            self.approve(market)
        market=self.scope(True)
        market["methods"].append("POST")
        with self.assertRaisesRegex(SourceBlocked,"SCOPE_EXCEEDS_PUBLIC_CONTRACT"):
            self.approve(market)

    def test_protected_storage_principal_and_permissions(self):
        with self.assertRaisesRegex(SourceBlocked,"STORAGE_IDENTITY_MISMATCH"):
            secure_storage(self.state,os.geteuid()+1,creating=True)
        self.root.chmod(0o755)
        with self.assertRaisesRegex(SourceBlocked,"LOCAL_STORAGE_DIRECTORY_NOT_PRIVATE"):
            secure_storage(self.state,os.geteuid(),creating=True)
        self.root.chmod(0o700)
        self.create_registry()
        self.state.chmod(0o644)
        with self.assertRaisesRegex(SourceBlocked,"LOCAL_STORAGE_FILE_NOT_PRIVATE"):
            secure_storage(self.state,os.geteuid())

    def test_preflight_live_and_revoke_short_circuit_under_audit_hook(self):
        script="""
import sys
from quant_personal_live_public_b5.cli import main
def check(event,args):
    if event.startswith('socket.') or event in ('open','sqlite3.connect','subprocess.Popen'):
        raise RuntimeError(event)
sys.addaudithook(check)
raise SystemExit(main(sys.argv[1:]))
"""
        for command in ("preflight","live-once","revoke"):
            env={**os.environ,"B5_ENABLED":"1","ACTIVATION_APPROVED":"1",
                 "HTTPS_PROXY":"http://127.0.0.1:7","BINANCE_API_KEY":"fake"}
            result=subprocess.run([sys.executable,"-c",script,command,"--scope",str(self.state)],
                                  env=env,capture_output=True,text=True,check=False)
            self.assertEqual((result.returncode,result.stdout,result.stderr.strip()),
                             (3,"","LIVE_CAPABILITY_NOT_ACTIVATED"))
            self.assertFalse(self.state.exists())


class EnrollmentTests(LocalTest):
    def test_lost_or_replaced_registry_cannot_reenroll(self):
        pin,_=self.enrollment()
        proof=self.approve(self.scope())
        self.assertEqual(enroll_once(pin,os.geteuid(),proof,self.state,self.create_registry),"REGISTERED")
        require_enrolled(pin,os.geteuid(),proof,self.state)
        old=self.root/"old-state"
        self.state.rename(old)
        with self.assertRaisesRegex(SourceBlocked,"ENROLLMENT_OR_REGISTRY_MISSING"):
            require_enrolled(pin,os.geteuid(),proof,self.state)
        with self.assertRaisesRegex(SourceBlocked,"ENROLLMENT_ALREADY_SPENT"):
            enroll_once(pin,os.geteuid(),proof,self.state,self.create_registry)
        self.create_registry()
        with self.assertRaisesRegex(SourceBlocked,"REGISTRY_ENROLLMENT_MISMATCH"):
            require_enrolled(pin,os.geteuid(),proof,self.state)

    def test_replacing_both_paths_does_not_recover(self):
        pin,body=self.enrollment()
        proof=self.approve(self.scope())
        enroll_once(pin,os.geteuid(),proof,self.state,self.create_registry)
        pin.path.rename(self.root/"old-anchor")
        pin.path.write_bytes(body)
        pin.path.chmod(0o600)
        self.state.unlink()
        with self.assertRaisesRegex(SourceBlocked,"ENROLLMENT_IDENTITY_MISMATCH"):
            enroll_once(pin,os.geteuid(),proof,self.state,self.create_registry)

    def test_failed_registration_keeps_spent_fence(self):
        pin,_=self.enrollment()
        proof=self.approve(self.scope())
        def crash():
            raise RuntimeError("simulated abrupt provisioning stop")
        with self.assertRaisesRegex(RuntimeError,"simulated"):
            enroll_once(pin,os.geteuid(),proof,self.state,crash)
        with self.assertRaisesRegex(SourceBlocked,"ENROLLMENT_ALREADY_SPENT"):
            enroll_once(pin,os.geteuid(),proof,self.state,self.create_registry)
        self.assertFalse(self.state.exists())

    def test_wrong_enrollment_principal(self):
        pin,_=self.enrollment()
        proof=self.approve(self.scope())
        with self.assertRaisesRegex(SourceBlocked,"ENROLLMENT_PRINCIPAL_MISMATCH"):
            enroll_once(pin,os.geteuid()+1,proof,self.state,self.create_registry)


class CanaryTests(LocalTest):
    def test_canary_completes_with_exact_two_without_publication_or_market(self):
        candidate=preview()
        self.assertEqual(candidate["nominal_full"],{"request_count":39,"known_weight":39,"funding_calls":3})
        active=self.active()
        publication=collect(active,"bootstrap",FixtureWire(self.clock),notify_stage=lambda: self.fail("market"))
        stage=publication["stage"]
        self.assertIsNone(stage["issue"])
        self.assertEqual(stage["market_status"],"NOT_EVALUATED")
        self.assertFalse(stage["activation_gate"]["market_authorized"])
        self.assertIsNone(publication["visible_venue_upper_ms"])
        self.assertEqual(stage["stats"]["reserved_requests"],2)
        with active.ledger.store.connect() as db:
            self.assertEqual([r[0] for r in db.execute("SELECT route FROM attempts ORDER BY id")],[TIME,INSTRUMENTS])
        with self.assertRaisesRegex(SourceBlocked,"STAGE2_NOT_AUTHORIZED"):
            active.reserve("bootstrap",publication["scan_id"],3,0,RouteRequest(TIME,{}),self.clock.sample())
        with self.assertRaisesRegex(DecisionError,"SOURCE_RUN_BLOCKED"):
            Adapter(active.ledger).read("BTCUSDT",scan=publication["scan_id"])

    def test_subbudget_enforces_first_two_before_market(self):
        active=self.active(True)
        scan,point=active.begin_phase("bootstrap")
        for request in (RouteRequest(INSTRUMENTS,{}), RouteRequest(DEPTH,{"symbol":"BTCUSDT","limit":5}),
                        RouteRequest(TIME,{},method="POST"), RouteRequest("/fapi/v1/order",{})):
            with self.subTest(route=request.route), self.assertRaises(SourceBlocked):
                active.reserve("bootstrap",scan,1,0,request,point)
        with self.assertRaisesRegex(SourceBlocked,"CANARY_REQUEST_SEQUENCE"):
            active.reserve("bootstrap",scan,1,1,RouteRequest(TIME,{}),point)
        with active.ledger.store.connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0],0)

    def test_full_stage2_uses_same_cutoff_matches_plan_and_replays(self):
        active=self.active(True)
        denied=[]
        def before_market():
            with active.ledger.store.connect() as db:
                denied.append(db.execute("SELECT COUNT(*) FROM h2a_canary").fetchone()[0])
            bad=RouteRequest(DEPTH,{"symbol":"BTCUSDT","limit":50})
            with self.assertRaisesRegex(SourceBlocked,"STAGE2_REQUEST_OUTSIDE_PLAN"):
                active.reserve("bootstrap",1,3,0,bad,self.clock.sample())
        publication=collect(active,"bootstrap",FixtureWire(self.clock),notify_stage=before_market)
        stage=publication["stage"]
        self.assertIsNone(stage["issue"])
        self.assertEqual(denied,[1])
        self.assertEqual((stage["stats"]["reserved_requests"],stage["stats"]["reserved_weight"]),(39,42))
        adapter=Adapter(active.ledger)
        b2=engine(adapter,self.root/"journal.sqlite")
        for symbol in SYMBOL_ORDER:
            market=adapter.read(symbol,scan=publication["scan_id"])
            self.assertEqual(market.source["activation_gate"],stage["activation_gate"])
            self.assertEqual(market.source["evidence"],QA)
            self.assertTrue(all(len(rows)==32 for rows in market.bars.values()))
            self.assertTrue(all(r.end_ms+2000<=market.cutoff_ms for bars in market.bars.values() for r in bars))
            card=b2.evaluate(symbol,scan=publication["scan_id"],as_of_ms=market.evaluated_ms)
            self.assertEqual(card["account_context_status"],"UNAVAILABLE")
            self.assertEqual(card["safe_position_size"],"UNKNOWN")
            self.assertNotEqual(card["evidence"],GENUINE)
        with self.assertRaisesRegex(DecisionError,"EVALUATION_MUST_USE_PUBLICATION_AS_OF"):
            adapter.read("BTCUSDT",scan=1,as_of_ms=publication["visible_venue_upper_ms"]-1)

    def test_revocation_on_boundary_preserves_two_attempts(self):
        active=self.active(True)
        publication=collect(active,"bootstrap",FixtureWire(self.clock),notify_stage=active.revoke)
        self.assertEqual(publication["stage"]["issue"]["code"],"ACTIVATION_REVOKED")
        reopened=Ledger.open_qa(self.state)
        with reopened.store.connect() as db:
            self.assertEqual(reopened.control(db)["state"],"REVOKED")
            self.assertEqual(db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0],2)

    def test_canary_denial_and_transient_do_not_dispatch_followups(self):
        for status in (403,418,429,451,503):
            self.state=self.root/f"{status}.sqlite"
            self.roots=replace(self.roots,state_path=self.state)
            active=self.active(True)
            def denial(_, __):
                return fixture_reply({},status=status,headers={"retry-after":"15"})
            publication=collect(active,"bootstrap",FixtureWire(self.clock,mutate=denial))
            with self.subTest(status=status):
                self.assertEqual(publication["stage"]["stats"]["reserved_requests"],1)
                self.assertNotIn("activation_gate",publication["stage"])
                with Ledger.open_qa(self.state).store.connect() as db:
                    self.assertEqual(db.execute("SELECT state FROM b5_control").fetchone()[0],"HALTED")
                    stop,hold=db.execute("SELECT stop,cooldown_hold FROM budget_epoch").fetchone()
                    if status in (403,418,451):
                        self.assertEqual(stop,f"HTTP_{status}")
                    if status==429:
                        self.assertEqual(hold,15_000)

    def test_mutated_marker_fails_closed_even_with_original_receipts(self):
        active=self.active(True)
        pub=collect(active,"bootstrap",FixtureWire(self.clock))
        adapter=Adapter(active.ledger)
        adapter.read("BTCUSDT",scan=pub["scan_id"])
        with sqlite3.connect(self.state) as db:
            with self.assertRaisesRegex(sqlite3.DatabaseError,"B5_APPEND_ONLY"):
                db.execute("UPDATE h2a_canary SET sha256='x'")
            db.execute("DROP TRIGGER lock_h2a_canary_UPDATE")
            db.execute("UPDATE h2a_canary SET sha256='x'")
        with self.assertRaisesRegex(DecisionError,"CANARY_PROOF_MISMATCH"):
            adapter.read("BTCUSDT",scan=pub["scan_id"])

    def test_abrupt_exit_after_claim_and_reserve_has_no_resume(self):
        approval=self.approve(self.scope())
        Ledger.qa(self.state,approval)
        script="""
from pathlib import Path
import os, sys
from quant_personal_public_b1.fixture import FixtureClock
from quant_personal_public_b1.session import RunIdentity
from quant_personal_live_public_b5.contract import RouteRequest
from quant_personal_live_public_b5.ledger import Active, Ledger
from quant_personal_live_public_b5.stages import StagePlan
from dataclasses import replace
from quant_personal_live_public_b5.offline import qa_approval
path=Path(sys.argv[1])
p, s, r, signed=sys.argv[2:]
base=qa_approval(path)
approval=replace(base,run_id=r,release=p,signed_sha256=signed,
                 scope=replace(base.scope,sha256=s,stage_plan=StagePlan(None,None)))
active=Active(Ledger.open_qa(path),approval,FixtureClock(),RunIdentity('qa-boot','qa-crashed'))
active.claim()
scan,point=active.begin_phase('bootstrap')
active.reserve('bootstrap',scan,1,0,RouteRequest('/fapi/v1/time',{}),point)
os._exit(19)
"""
        completed=subprocess.run([sys.executable,"-c",script,str(self.state),approval.release,
                                  approval.scope.sha256,approval.run_id,approval.signed_sha256],check=False)
        self.assertEqual(completed.returncode,19)
        reopened=Active(Ledger.open_qa(self.state),approval,self.clock,RunIdentity("qa-reboot","qa-new"))
        with self.assertRaisesRegex(SourceBlocked,"ACTIVATION_CONSUMED_OR_REVOKED"):
            reopened.claim()
        with self.assertRaisesRegex(SourceBlocked,"ACTIVATION_PROCESS_OWNERSHIP"):
            reopened.begin_phase("bootstrap")
        with reopened.ledger.store.connect() as db:
            attempt=db.execute("SELECT route,response,weight FROM attempts").fetchone()
            self.assertEqual(tuple(attempt),(TIME,None,1))
