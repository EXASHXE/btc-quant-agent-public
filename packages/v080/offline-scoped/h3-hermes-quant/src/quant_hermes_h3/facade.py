"""Serve the frozen V1 facade in a separate offline Core process."""

import multiprocessing
import os
from contextlib import contextmanager
from pathlib import Path

from quant_hermes_feishu_h1.contract import V1_READ_ONLY_TOOLS, ContractError
from quant_hermes_feishu_h1.facade import (
    PrincipalPolicy,
    QuantFacadeClient,
    QuantFacadeService,
    QuantUdsServer,
)
from quant_hermes_feishu_h1.journal_reader import ApprovedJournalRegistry, ApprovedJournalSource
from quant_personal_live_public_b5.contract import QA
from quant_personal_live_public_b5.decision import replay

from .source import offline_adapter

SOCKET = Path("ipc/f.sock")
PRINCIPAL = "hermes_quant_plugin"


class RawVerifiedRegistry(ApprovedJournalRegistry):
    """Keep H1 projection and V1 semantics. Additionally replay upstream raw evidence."""

    def __init__(self, source, journal):
        super().__init__([ApprovedJournalSource("h3_offline", journal)])
        self.adapter = offline_adapter(source)

    def load_all_verified_cards(self):
        records, latest = super().load_all_verified_cards()
        for record in records:
            card = record.card
            if record.source_evidence_class != QA or card["source_lane"] != QA:
                raise ContractError("INTEGRITY_FAILURE", "H3 fixture evidence class mismatch")
            if card.get("evaluation_receipt") is None:
                if card["market_status"] in {"WATCH", "EXECUTABLE", "INVALID"}:
                    raise ContractError("INTEGRITY_FAILURE", "Card lacks admitted source")
                continue
            try:
                replay(self.adapter, card)
            except Exception:  # noqa: BLE001 - redact all storage/parser failures at the facade.
                raise ContractError(
                    "INTEGRITY_FAILURE", "Accepted raw source replay failed"
                ) from None
        return records, latest


def _serve(source, journal, ready):
    try:
        uid = frozenset({os.getuid()})
        scopes = frozenset({"owner_dm", "outbox_worker"})
        read_only = frozenset(V1_READ_ONLY_TOOLS)
        policy = [PrincipalPolicy(PRINCIPAL, uid, scopes, read_only, 240)]
        service = QuantFacadeService(RawVerifiedRegistry(source, journal), principals=policy)
        with QuantUdsServer(SOCKET, service) as server:
            ready.send(True)
            ready.close()
            server.serve_forever()
    finally:
        ready.close()


@contextmanager
def serving(source, journal):
    """Use a private, relative UDS path to stay below the Linux sun_path limit."""
    ctx = multiprocessing.get_context("fork")
    receive, send = ctx.Pipe(duplex=False)
    process = ctx.Process(target=_serve, args=(source, journal, send), name="quant-h3-offline-core")
    process.start()
    send.close()
    try:
        if not receive.poll(5) or not receive.recv():
            raise RuntimeError("FACADE_STARTUP_FAILED")
        yield QuantFacadeClient(SOCKET, principal_id=PRINCIPAL, timeout_s=1.0)
    finally:
        receive.close()
        process.terminate()
        process.join(3)
        if process.is_alive():
            process.kill()
            process.join()
        SOCKET.unlink(missing_ok=True)
