"""Install and exercise post3 with the accepted A1 mock wire and native signatures."""

import hashlib
import sqlite3
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import test_a1 as base
from quant_personal_live_public_b5 import egress, live, trust
from quant_personal_public_b1.policy import SourceBlocked

from quant_h4.fence import FilePin, Witness

setUpModule = base.setUpModule


class Canary(base.Scenario):
    def setUp(self):
        super().setUp()
        independent = tempfile.TemporaryDirectory()
        self.addCleanup(independent.cleanup)
        path = Path(independent.name) / "independent"
        body = b"H4_WITNESS_V1 canary-rollback-fixture\n"
        path.write_bytes(body)
        self.roots = replace(
            self.roots,
            rollback_witness=Witness(
                FilePin.capture_fixture(path), hashlib.sha256(body).hexdigest(), fixture_only=True
            ),
        )

    def test_simultaneous_same_inode_sqlite_and_enrollment_rollback(self):
        args = self.stage()
        with (
            self.rehearsal() as (dns, socket),
            base.patch.object(egress, "_exchange", side_effect=self.mock_exchange),
        ):
            self.register(args)
            db_inode, anchor_inode = self.state.stat().st_ino, self.anchor.stat().st_ino
            initial_anchor = self.anchor.read_bytes()
            with sqlite3.connect(":memory:") as backup, sqlite3.connect(self.state) as db:
                db.backup(backup)
                result = live.live_once(*args, progress=lambda _: None)
                self.assertEqual((result["source_status"], result["cards"]), ("NOT_EVALUATED", []))
                backup.backup(db)
                self.anchor.write_bytes(initial_anchor)
            self.assertEqual(
                (self.state.stat().st_ino, self.anchor.stat().st_ino), (db_inode, anchor_inode)
            )
            dns.reset_mock()
            socket.reset_mock()
            with self.assertRaisesRegex(SourceBlocked, "CAPABILITY_SPENT"):
                live.preflight(*args)
            with self.assertRaisesRegex(SourceBlocked, "CAPABILITY_SPENT"):
                live.live_once(*args, progress=lambda _: None)
            dns.assert_not_called()
            socket.assert_not_called()

    def test_alternate_grant_reusing_run_id_cannot_reenroll(self):
        args = self.stage()
        with self.rehearsal() as (dns, socket):
            self.register(args)
            live._active(*args).claim()
            changed = self.envelope(expires_ms=self.clock.wall_ms + 15_000)
            with self.assertRaisesRegex(SourceBlocked, "CAPABILITY_SPENT"):
                live.provision_reviewed_state(*self.stage(changed))
            with self.assertRaisesRegex(SourceBlocked, "ENROLLMENT_SPENT"):
                live.preflight(*self.stage())
            dns.assert_not_called()
            socket.assert_not_called()

    def test_missing_witness_fails_before_dns(self):
        args = self.stage()
        with self.rehearsal() as (dns, socket):
            self.register(args)
            self.roots.rollback_witness.pin.path.unlink()
            with self.assertRaisesRegex(SourceBlocked, "WITNESS_UNAVAILABLE_OR_BUSY"):
                live.live_once(*args, progress=lambda _: None)
            dns.assert_not_called()
            socket.assert_not_called()

    def test_fixture_witness_never_provisions_production(self):
        candidate = replace(
            self.roots, local_uid=1009, owner_ed25519=b"a" * 32, controller_ed25519=b"b" * 32
        )
        with (
            base.patch.object(trust, "_PROVISIONED", candidate),
            base.patch.object(trust, "_A1_BUILD_MODE", "OWNER_LOCAL_REVIEWED_A1"),
        ):
            with self.assertRaisesRegex(SourceBlocked, "H4_PROTECTED_ROLLBACK_WITNESS_REQUIRED"):
                trust.production_roots()


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Canary)
    status = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(not status.wasSuccessful())
