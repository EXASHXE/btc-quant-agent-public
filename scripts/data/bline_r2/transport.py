"""Bounded, resumable static-file transport. No accounts, streams or redirects."""
from __future__ import annotations

import hashlib
import http.client
import io
import json
import re
import shutil
import threading
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, Request, build_opener

from tools.data.common import NoRedirectHandler

CAP_BYTES = 256_000_000_000
FREE_FLOOR = 400*1024**3
MAX_OBJECT = 64*1024**2
EXPANSION_RESERVE = 4*512*1024**2  # streaming CRC/CSV QC; no on-disk extraction
HOSTS = {"data.binance.vision", "static.okx.com"}


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def now() -> str:
    return datetime.now(UTC).isoformat()


def retry_after_seconds(value: str) -> int:
    if value.isdigit():
        return int(value)
    try:
        delay = (parsedate_to_datetime(value)-datetime.now(UTC)).total_seconds()
        return max(0,int(delay)+int(delay % 1 > 0))
    except (TypeError,ValueError,OverflowError):
        return 60


def json_bytes(value) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)+"\n").encode()


def immutable_json(path: Path, value) -> None:
    raw = json_bytes(value)
    if path.exists():
        if path.read_bytes() != raw:
            raise ValueError("REFUSE_OVERWRITE:"+str(path))
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(raw)


class SourceBlocked(Exception):
    pass


class Transport:
    def __init__(self, root: Path, *, direct=False, requests_per_second=8.0,
                 disk_usage=shutil.disk_usage):
        if not 0 < requests_per_second <= 8:
            raise ValueError("LOCAL_RATE_CAP_8_REQUESTS_PER_SECOND")
        self.root, self.disk_usage = root, disk_usage
        self.lock = threading.Lock()
        self.delay = 1/requests_per_second
        self.next_request = 0.0
        self.requests = self.network_bytes = 0
        self.stored = sum(p.stat().st_size for p in root.rglob("*") if p.is_file())
        self.blocked = {}
        self.failures = {}
        self.direct = direct
        self.local = threading.local()

    @contextmanager
    def _pooled_direct(self, url, headers):
        parsed = urlsplit(url)
        connections = getattr(self.local,"connections",None)
        if connections is None:
            connections = self.local.connections = {}
        if parsed.hostname not in connections:
            connections[parsed.hostname] = http.client.HTTPSConnection(parsed.hostname,timeout=20)
        connection = connections[parsed.hostname]
        response = None
        try:
            target = parsed.path+("?"+parsed.query if parsed.query else "")
            connection.request("GET",target,headers=headers)
            response = connection.getresponse()
            if response.status not in (200,206):
                payload = response.read(8192)
                raise HTTPError(url,response.status,response.reason,response.headers,io.BytesIO(payload))
            yield response
        except (OSError,http.client.HTTPException) as exc:
            connection.close()
            if isinstance(exc,http.client.HTTPException):
                raise OSError("HTTP_CONNECTION_RESET:"+type(exc).__name__) from exc
            raise
        finally:
            if response is not None:
                if response.fp is not None:
                    connection.close()  # unconsumed/oversized body cannot poison the next response
                response.close()

    def check_storage(self, incoming=0):
        # Reserve temporary expansion and metadata even though QC is streamed.
        if self.stored+incoming+EXPANSION_RESERVE+1024**3 > CAP_BYTES:
            raise SourceBlocked("STORAGE_256_GB_CAP")
        if self.disk_usage(self.root).free-incoming-EXPANSION_RESERVE < FREE_FLOOR:
            raise SourceBlocked("FREE_DISK_400_GIB_FLOOR")

    def _open(self, url, family, headers=None):
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.hostname not in HOSTS or parsed.username or parsed.password:
            raise ValueError("OFFICIAL_ARCHIVE_ORIGIN_ONLY")
        if parsed.hostname == "data.binance.vision" and not parsed.path.startswith("/data/"):
            raise ValueError("STATIC_ARCHIVE_PATH_ONLY")
        if parsed.hostname == "static.okx.com" and not parsed.path.startswith("/cdn/"):
            raise ValueError("STATIC_ARCHIVE_PATH_ONLY")
        with self.lock:
            if family in self.blocked:
                raise SourceBlocked(self.blocked[family])
            self.check_storage()
            if self.requests >= 20000:
                raise SourceBlocked("REQUEST_BUDGET_20000")
            delay = max(0.0, self.next_request-time.monotonic())
            self.next_request = max(self.next_request, time.monotonic())+self.delay
            self.requests += 1
        if delay:
            time.sleep(delay)
        handlers = [NoRedirectHandler()]
        if self.direct:
            handlers.append(ProxyHandler({}))
        opener = build_opener(*handlers)
        request_headers = {"User-Agent": "quant-v065-bline-r2-personal-research/1.0",
            "Accept-Encoding": "identity", **(headers or {})}
        if self.direct:
            return self._pooled_direct(url,request_headers)
        request = Request(url, headers=request_headers)
        return opener.open(request, timeout=20)

    def metadata(self, url, family, *, limit=8192):
        for attempt in range(3):
            try:
                with self._open(url, family) as response:
                    raw = response.read(limit+1)
                    if len(raw) > limit:
                        raise ValueError("METADATA_SIZE_LIMIT")
                    with self.lock:
                        self.network_bytes += len(raw)
                    return raw, dict(response.headers)
            except HTTPError as exc:
                if exc.code == 404:
                    return None, {"http_status": 404}
                if exc.code in (401, 403, 451):
                    self.blocked[family] = f"PROVIDER_ACCESS_DENIED_HTTP_{exc.code}"
                    raise SourceBlocked(self.blocked[family]) from exc
                if exc.code == 429:
                    retry = exc.headers.get("Retry-After", "60")
                    pause = retry_after_seconds(retry)
                    if pause > 60 or attempt == 2:
                        self.blocked[family] = "PROVIDER_RATE_LIMIT_HOLD"
                        raise SourceBlocked(self.blocked[family]) from exc
                    with self.lock:
                        self.next_request = max(self.next_request,time.monotonic()+pause)
                elif exc.code < 500 or attempt == 2:
                    raise
            except (OSError, TimeoutError) as exc:
                if attempt == 2:
                    with self.lock:
                        self.failures[family] = self.failures.get(family, 0)+1
                        if self.failures[family] >= 3:
                            self.blocked[family] = "SOURCE_NETWORK_ACCESS_BLOCKED:"+type(exc).__name__
                    raise
            time.sleep(2**attempt)
        raise SourceBlocked("RETRIES_EXHAUSTED")

    def archive(self, url, family, destination: Path, expected_sha: str | None):
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            actual = digest(destination)
            if expected_sha is not None and actual != expected_sha:
                raise ValueError("EXISTING_ARCHIVE_SHA_MISMATCH")
            return {"bytes":destination.stat().st_size, "sha256":actual, "reused":True}
        part = destination.with_name(destination.name+".part")
        meta = part.with_name(part.name+".json")
        if part.exists():
            pinned = json.loads(meta.read_text()) if meta.exists() else {}
            if pinned.get("url") != url or pinned.get("expected_sha256") != expected_sha:
                raise ValueError("PARTIAL_IDENTITY_MISMATCH")
        for attempt in range(3):
            offset = part.stat().st_size if part.exists() else 0
            headers = {"Range":f"bytes={offset}-"} if offset else {}
            if offset and meta.exists():
                etag = json.loads(meta.read_text()).get("etag")
                if etag and not etag.startswith("W/"):
                    headers["If-Range"] = etag
            try:
                with self._open(url, family, headers) as response:
                    length = response.headers.get("Content-Length")
                    length = int(length) if length and length.isdigit() else None
                    append = response.status == 206
                    if append:
                        cr = response.headers.get("Content-Range", "")
                        match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", cr)
                        if not match or int(match[1]) != offset:
                            raise ValueError("INVALID_RESUME_CONTENT_RANGE")
                    elif response.status != 200:
                        raise ValueError("UNEXPECTED_ARCHIVE_STATUS")
                    else:
                        with self.lock:
                            self.stored -= offset
                        offset = 0
                    total = offset+(length or MAX_OBJECT)
                    if total > MAX_OBJECT:
                        raise SourceBlocked("OBJECT_OVER_64_MIB_DEFERRED_BENEFIT_REVIEW")
                    with self.lock:
                        self.check_storage(total-offset)
                    meta.write_bytes(json_bytes({"url":url,"expected_sha256":expected_sha,
                        "etag":response.headers.get("ETag"),"last_modified":response.headers.get("Last-Modified")}))
                    received = 0
                    with part.open("ab" if append else "wb") as stream:
                        for block in iter(lambda:response.read(65536), b""):
                            if offset+received+len(block) > MAX_OBJECT:
                                raise SourceBlocked("OBJECT_SIZE_STREAM_LIMIT")
                            with self.lock:
                                self.check_storage(len(block))
                                self.network_bytes += len(block)
                                self.stored += len(block)
                            stream.write(block)
                            received += len(block)
                    if length is not None and received != length:
                        raise OSError("TRUNCATED_RESPONSE_RESUMABLE")
                    actual = digest(part)
                    if expected_sha is not None and actual != expected_sha:
                        raise ValueError("PUBLISHER_SHA256_MISMATCH")
                    part.rename(destination)
                    meta.unlink()
                    return {"bytes":destination.stat().st_size, "sha256":actual, "reused":False,
                        "etag":response.headers.get("ETag"),"last_modified":response.headers.get("Last-Modified"),
                        "downloaded_at_utc":now(),"resumed_from_bytes":offset,"attempts":attempt+1}
            except HTTPError as exc:
                if exc.code in (401,403,451):
                    self.blocked[family] = f"PROVIDER_ACCESS_DENIED_HTTP_{exc.code}"
                    raise SourceBlocked(self.blocked[family]) from exc
                if exc.code == 404:
                    return None
                if exc.code == 429:
                    pause = retry_after_seconds(exc.headers.get("Retry-After", "60"))
                    if pause>60 or attempt == 2:
                        self.blocked[family] = "PROVIDER_RATE_LIMIT_HOLD"
                        raise SourceBlocked(self.blocked[family]) from exc
                    with self.lock:
                        self.next_request = max(self.next_request,time.monotonic()+pause)
                elif exc.code < 500 or attempt == 2:
                    raise
            except (OSError, TimeoutError) as exc:
                if attempt == 2:
                    with self.lock:
                        self.failures[family] = self.failures.get(family,0)+1
                        if self.failures[family] >= 3:
                            self.blocked[family] = "SOURCE_NETWORK_ACCESS_BLOCKED:"+type(exc).__name__
                    raise
            time.sleep(2**attempt)
        raise SourceBlocked("ARCHIVE_RETRIES_EXHAUSTED")
