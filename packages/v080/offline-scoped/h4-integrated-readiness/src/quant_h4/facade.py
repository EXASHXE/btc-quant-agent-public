"""Use the frozen H1 V1 envelope on a peer-checked UNIX connection."""

import json
import socket
import struct
from contextlib import contextmanager

from quant_hermes_feishu_h1.contract import (
    MAX_REQUEST_BYTES,
    MAX_RESPONSE_BYTES,
    V1_READ_ONLY_TOOLS,
    ContractError,
)
from quant_hermes_feishu_h1.facade import QuantFacadeClient, _recv_exact

from .fence import Denied


class PeerVerifiedFacade(QuantFacadeClient):
    def __init__(self, native, permit):
        claim = permit.claim
        if (
            type(native) is not QuantFacadeClient
            or native.principal_id != "hermes_quant_plugin"
            or str(native.socket_path.resolve(strict=True)) != claim.facade_path
        ):
            raise Denied("FACADE_BINDING_MISMATCH")
        super().__init__(
            claim.facade_path,
            principal_id=native.principal_id,
            recipient_scope="owner_dm",
            timeout_s=min(1.0, native.timeout_s),
        )
        self._uid = claim.facade_uid

    @contextmanager
    def _connection(self):
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                connection.settimeout(self.timeout_s)
                connection.connect(str(self.socket_path))
                _, uid, _ = struct.unpack(
                    "3i", connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
                )
                if uid != self._uid:
                    raise Denied("FACADE_PEER_UID_MISMATCH")
                yield connection
        except OSError as exc:
            raise Denied("FACADE_CONNECTION_UNAVAILABLE") from exc

    def probe(self):
        with self._connection():
            pass

    def send_raw_envelope(self, raw_req):
        if raw_req.get("tool") not in V1_READ_ONLY_TOOLS:
            raise ContractError("UNAUTHORIZED", "H4 facade is V1 read-only")
        payload = json.dumps(raw_req, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(payload) > MAX_REQUEST_BYTES:
            raise ContractError("INVALID_ARGUMENT", "Client request exceeds max request size")
        with self._connection() as connection:
            connection.sendall(struct.pack("!I", len(payload)) + payload)
            header = _recv_exact(connection, 4)
            if len(header) != 4:
                raise ContractError("SOURCE_UNAVAILABLE", "Truncated facade header")
            (size,) = struct.unpack("!I", header)
            if not 0 < size <= MAX_RESPONSE_BYTES * 2:
                raise ContractError("INTEGRITY_FAILURE", "Unexpected facade response length")
            raw = _recv_exact(connection, size)
            if len(raw) != size:
                raise ContractError("SOURCE_UNAVAILABLE", "Truncated facade response")
            try:
                decoded = json.loads(raw)
            except (ValueError, UnicodeError) as exc:
                raise ContractError("INTEGRITY_FAILURE", "Invalid facade response") from exc
            if type(decoded) is not dict:
                raise ContractError("INTEGRITY_FAILURE", "Invalid facade envelope")
            return decoded
