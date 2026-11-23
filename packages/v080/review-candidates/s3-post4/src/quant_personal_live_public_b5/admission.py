"""Bind B5 wire receipts and durable publication to B2 Market inputs."""

from __future__ import annotations

import json
import sqlite3

from quant_personal_decision_b2.model import DecisionError, Market, integer
from quant_personal_public_b1.policy import SourceBlocked, require
from quant_personal_public_b1.store import encode, sha
from quant_personal_public_b1.wire import json_body
from quant_personal_public_bridge_b4 import normalize as norm
from quant_personal_public_bridge_b4.admission import Attempt, Reader as CausalReader, chronology, ms
from quant_personal_public_bridge_b4.session import POLICY

from .contract import CONTRACT, GENUINE, GENUINE_RECEIPT, HOST, INTERVALS, QA, QA_RECEIPT, SYMBOLS, RouteRequest, digest, sha_text
from .stages import STAGE_CONTRACT
from .trust import production_roots

ADAPTER = "B5_PUBLIC_TO_B2_CAUSAL_V1"


def _check_physical(tls, approval, roots):
    route = approval.scope.route
    require(type(tls) is dict and tls.get("sni") == HOST and tls.get("authority") == HOST+":443"
            and tls.get("egress_id") == route.egress_id and tls.get("interface") == route.interface
            and tls.get("netns_inode") == str(route.netns_inode) and tls.get("source_ipv4") == route.source_address
            and tls.get("resolver_ipv4") == route.resolver_address
            and tls.get("route_table_sha256") == route.route_table_sha256
            and tls.get("ca_sha256") == roots.ca_bundle_sha256
            and tls.get("protocol") in ("TLSv1.2", "TLSv1.3") and sha_text(tls.get("certificate_sha256"))
            and tls.get("verification") == "CERT_REQUIRED_AND_HOSTNAME", "UNQUALIFIED_PHYSICAL_ORIGIN")
    answers = tls.get("resolved_ipv4", "").split(",")
    require(answers == sorted(set(answers)) and set(answers) <= set(route.peers)
            and tls.get("peer") in answers, "PHYSICAL_DNS_BINDING_MISMATCH")


class Reader(CausalReader):
    def __init__(self, ledger, db, *, approval=None, roots=None):
        super().__init__(ledger, db)
        self.approval, self.roots = approval, roots
        self.claimed = None
        if ledger.origin == GENUINE:
            require(roots is production_roots() and approval is not None, "UNQUALIFIED_PHYSICAL_ORIGIN")
            row = ledger.verify_registration(db, approval, roots)
            require(row["claimed"] is not None and row["state"] != "AVAILABLE", "ACTIVATION_NOT_CONSUMED")
            self.claimed = json.loads(row["claimed"])
        self.peer = None

    def attempt(self, ident, scan, route):
        integer(ident, "receipt", minimum=1)
        if ident not in self.attempts:
            row = self.db.execute("""SELECT a.*,s.stamp AS sent,o.starting AS started,r.payload,r.sha256,
                                    p.phase FROM attempts a JOIN b4_sends s ON s.attempt=a.id
                                    JOIN scans o ON o.id=a.scan_id JOIN b5_receipts r ON r.attempt=a.id
                                    JOIN b5_phases p ON p.scan_id=a.scan_id WHERE a.id=?""", (ident,)).fetchone()
            require(row is not None and row["raw"] is not None and row["response"] is not None,
                    "SOURCE_RECEIPT_MISSING")
            response, proof = json.loads(row["response"]), json.loads(row["payload"])
            raw, encoded = row["raw"], row["encoded"]
            raw_sha = sha(raw)
            encoded_sha = sha(encoded) if encoded is not None else None
            require(0 < len(raw) <= POLICY.max_body_bytes and raw_sha == response["body_sha256"]
                    and encoded_sha == response["encoded_sha256"] and response["status"] == 200
                    and response["error"] is None and response["headers"].get("content-type","")
                    .split(";",1)[0].strip().lower() == "application/json", "SOURCE_RAW_DIGEST_OR_STATUS")
            request = json.loads(row["request"])
            debit = self.approval.scope.funding_debit if self.approval is not None else row["weight"]
            req = RouteRequest(row["route"], **request, funding_debit=debit)
            weight, wire = req.validate()
            require(weight == row["weight"] and row["egress"] == self.ledger.store.egress, "SOURCE_REQUEST_BINDING")
            sent, recv = json.loads(row["sent"]), response["receipt"]
            reserved = json.loads(row["reserved"])
            chronology(json.loads(row["started"]), reserved, sent, recv)
            require(ms(recv).mono_ms-ms(sent).mono_ms <= POLICY.request_timeout_ms, "SOURCE_REQUEST_DEADLINE")
            checked = {
                "schema": GENUINE_RECEIPT if self.ledger.origin == GENUINE else QA_RECEIPT,
                "origin": self.ledger.origin, "run_id": self.ledger.run_id, "phase": row["phase"],
                "scan_id": row["scan_id"], "attempt": ident, "request": request, "url": req.url,
                "wire_sha256": sha(wire), "planned_weight": weight, "signed_sha256": self.ledger.signed_sha,
                "status": 200, "raw_sha256": raw_sha, "encoded_sha256": encoded_sha,
                "wire_bytes": response["wire_bytes"], "headers": response["headers"], "issue": None,
                "tls": response["tls"], "request_start": sent, "receive": recv,
            }
            require(proof == checked and row["sha256"] == digest(proof), "RECEIPT_DIGEST_OR_BINDING")
            if self.ledger.origin == GENUINE:
                chronology(self.claimed, json.loads(row["started"]), reserved, sent, recv)
                self.approval.valid_at(ms(sent).wall_ms)
                self.approval.valid_at(ms(recv).wall_ms)
                _check_physical(proof["tls"], self.approval, self.roots)
                got = proof["tls"]["peer"]
                if self.peer is not None:
                    require(got == self.peer, "PHYSICAL_PEER_CHANGED")
                self.peer = got
            else:
                # B5 fixture rows never originate from the physical path, even if
                # a test socket completed a real TLS handshake.
                require(proof["origin"] == QA, "UNQUALIFIED_QA_RECEIPT")
            meta = {**proof, "receipt_id": ident, "source_scan_id": row["scan_id"], "route": req.route,
                    "reservation": reserved, "receipt_sha256": row["sha256"]}
            self.attempts[ident] = Attempt(ident, row["scan_id"], req, json_body(raw), meta)
        result = self.attempts[ident]
        require((result.scan, result.request.route) == (scan, route), "SOURCE_RECEIPT_BINDING")
        return result

    def market(self, symbol, scan, requested_as_of, publication_sha=None):
        pub, actual_sha, first = self.publication(scan)
        require(publication_sha is None or actual_sha == publication_sha, "PUBLICATION_DIGEST_MISMATCH")
        if self.approval is not None:
            self.approval.valid_at(ms(pub["published"]).wall_ms)
        gate = pub["stage"].get("activation_gate")
        marker = self.db.execute("SELECT payload,sha256 FROM h2a_canary WHERE scan_id=?", (scan,)).fetchone()
        if marker is not None or gate is not None or self.ledger.origin == GENUINE:
            require(marker is not None and gate == json.loads(marker["payload"])
                    and digest(gate) == marker["sha256"] and gate["schema"] == STAGE_CONTRACT
                    and gate["market_authorized"] is True and gate["cutoff_venue_ms"] == first.lower_ms,
                    "CANARY_PROOF_MISMATCH")
            control = self.ledger.control(self.db)
            require(gate["scope_sha256"] == control["scope_sha"], "CANARY_PROOF_MISMATCH")
            from .stages import CANARY_ROUTES

            ids = (gate["time_receipt"],gate["metadata_receipt"])
            require(ids[0] < ids[1] and ids[0] == pub["stage"]["clock"]["first_id"],
                    "CANARY_PROOF_MISMATCH")
            certified = [self.attempt(ident,scan,route) for ident,route in zip(ids,CANARY_ROUTES,strict=True)]
            require([item.proof["receipt_sha256"] for item in certified] == gate["receipt_sha256"],
                    "CANARY_PROOF_MISMATCH")
        visible = pub["visible_venue_upper_ms"]
        as_of = visible if requested_as_of is None else requested_as_of
        require(as_of == visible, "EVALUATION_MUST_USE_PUBLICATION_AS_OF")
        raw_market = pub["stage"]["markets"].get(symbol)
        require(raw_market is not None and not raw_market["issue"], "SYMBOL_INPUT_BLOCKED",
                str(raw_market and raw_market["issue"]))
        frames, obs = raw_market["frames"], raw_market["observations"]
        require(frames.keys() == INTERVALS.keys() and obs.keys() == norm.OBSERVATIONS.keys(),
                "MISSING_FRAME_OR_OBSERVATION")
        bars = {frame: self.frame(symbol, frame, refs, scan, first.lower_ms, as_of)
                for frame, refs in frames.items()}
        normalized = {}
        for name, route in norm.OBSERVATIONS.items():
            ref = obs[name]
            got, _, seen, proof, _ = self.timing(ref, route, scan, as_of)
            original, _, _ = self.publication(got.scan)
            require(original["stage"]["markets"][symbol]["observations"].get(name) == ref,
                    "CONTEXT_FIRST_PUBLICATION_BINDING")
            rebuilt, values = norm.observation_ref(got.seq, got.scan, proof["raw_sha256"], got.request,
                                                     got.raw, symbol, seen)
            require(rebuilt == ref, "SOURCE_CONTEXT_DIGEST")
            norm.validate_age(name, ref, as_of)
            normalized[name] = {**proof, **rebuilt, "values": json.loads(encode(values))}
        norm.coherent(normalized)
        source = {
            "schema": "B5_EVALUATION_RECEIPT_V1", "adapter": ADAPTER, "source_origin": self.ledger.origin,
            "evidence": self.ledger.origin, "warnings": self.ledger.warnings, "contract": CONTRACT,
            "run_id": pub["run_id"], "source_lineage": self.ledger.lineage,
            "source_scan_id": scan, "source_publication_sha256": actual_sha,
            "normalized_symbol_sha256": digest(raw_market), "bar_cutoff_venue_ms": first.lower_ms,
            "evaluation_venue_ms": as_of, "source_published_venue_ms": visible,
            "source_clock": pub["stage"]["clock"], "source_published": pub["published"],
            "source_durable_availability": pub["commit_observed"],
            "raw_receipts": [self.used[k] for k in sorted(self.used)],
        }
        if gate is not None:
            source["activation_gate"] = gate
        return Market(symbol, as_of, first.lower_ms, source, bars, normalized, True)


class Adapter:
    def __init__(self, ledger, *, approval=None, roots=None):
        self.ledger = ledger
        self.approval, self.roots = approval, roots
        if ledger.origin == GENUINE:
            require(roots is production_roots() and approval is not None
                    and ledger.store.path == roots.state_path, "UNQUALIFIED_PHYSICAL_ORIGIN")
        else:
            require(ledger.origin == QA and approval is None and roots is None, "UNQUALIFIED_QA_LEDGER")

    def read(self, symbol, *, scan=None, as_of_ms=None, publication_sha=None):
        if symbol not in SYMBOLS:
            raise DecisionError("UNQUALIFIED_SYMBOL", str(symbol))
        if scan is not None:
            integer(scan, "scan", minimum=1)
        if as_of_ms is not None:
            integer(as_of_ms, "as_of", minimum=1)
        try:
            with self.ledger.store.connect() as db:
                db.execute("BEGIN")
                if self.approval is not None:
                    self.ledger.binding(self.ledger.control(db), self.approval)
                found = self.ledger.publication(scan, as_of_ms if scan is None else None, db=db)
                require(found is not None, "NO_DURABLE_PUBLICATION_AS_OF")
                return Reader(self.ledger, db, approval=self.approval, roots=self.roots).market(
                    symbol, found[0]["scan_id"], as_of_ms, publication_sha)
        except SourceBlocked as exc:
            raise DecisionError(exc.code, exc.detail) from exc
        except (sqlite3.Error, ValueError, KeyError, TypeError, AttributeError, RecursionError, OverflowError) as exc:
            if isinstance(exc, DecisionError):
                raise
            raise DecisionError("B5_SOURCE_EVIDENCE_INVALID", type(exc).__name__) from exc

    def rejected_reference(self, *, scan, as_of_ms):
        try:
            found = self.ledger.publication(scan, as_of_ms if scan is None else None)
            if found:
                return {"scan": found[0]["scan_id"], "publication_sha256": found[1],
                        "reason": found[0]["stage"]["issue"], "usable_for_evaluation": False}
        except (ValueError, sqlite3.Error, KeyError, TypeError):
            pass
        return None
