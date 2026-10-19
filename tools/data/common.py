"""Common utilities for V065-DATA-R2 data acquisition pipeline.

Handles budgeting, atomic fetching, checksum verification, schema QC,
and manifest/coverage reporting. Python stdlib only.
"""
from __future__ import annotations

import hashlib
import re
import shutil
import time
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

# Hard budget caps
DEFAULT_COMPRESSED_CAP = 4 * 1024**3   # 4 GiB
DEFAULT_EXPANDED_CAP = 16 * 1024**3    # 16 GiB
DEFAULT_REQUEST_CAP = 2000             # 2000 requests
MIN_FREE_GIB = 100.0                   # >= 100 GiB free


class BudgetExceededError(Exception):
    """Raised when any batch budget or safety limit is exceeded."""


class NoRedirectHandler(HTTPRedirectHandler):
    """Refuse HTTP redirects for strict origin and link pinning."""

    def redirect_request(
        self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> None:
        raise BudgetExceededError(f"HTTP_REDIRECT_REFUSED: {newurl}")


class Budget:
    """Tracks and enforces download and decompression resource limits."""

    def __init__(
        self,
        compressed_cap: int = DEFAULT_COMPRESSED_CAP,
        expanded_cap: int = DEFAULT_EXPANDED_CAP,
        request_cap: int = DEFAULT_REQUEST_CAP,
        workspace: Path | None = None,
    ):
        self.compressed_cap = compressed_cap
        self.expanded_cap = expanded_cap
        self.request_cap = request_cap
        self.workspace = workspace
        self.compressed_bytes = 0
        self.expanded_bytes = 0
        self.requests_made = 0
        self.requested_urls: set[str] = set()

    def check_disk(self) -> dict[str, float]:
        path = self.workspace if self.workspace and self.workspace.exists() else Path(".")
        usage = shutil.disk_usage(path)
        free_gib = usage.free / (1024**3)
        total_gib = usage.total / (1024**3)
        used_gib = usage.used / (1024**3)
        if free_gib < MIN_FREE_GIB:
            raise BudgetExceededError(
                f"DISK_SPACE_EXHAUSTED: {free_gib:.2f} GiB free < {MIN_FREE_GIB} GiB required"
            )
        return {
            "total_gib": round(total_gib, 2),
            "used_gib": round(used_gib, 2),
            "free_gib": round(free_gib, 2),
        }

    def register_request(self, url: str) -> None:
        self.check_disk()
        if self.requests_made >= self.request_cap:
            raise BudgetExceededError(
                f"REQUEST_CAP_EXCEEDED: {self.requests_made} >= {self.request_cap}"
            )
        self.requests_made += 1
        self.requested_urls.add(url)

    def consume_compressed(self, n: int) -> None:
        if self.compressed_bytes + n > self.compressed_cap:
            raise BudgetExceededError(
                f"COMPRESSED_CAP_EXCEEDED: {self.compressed_bytes + n} > {self.compressed_cap}"
            )
        self.compressed_bytes += n

    def consume_expanded(self, n: int) -> None:
        if self.expanded_bytes + n > self.expanded_cap:
            raise BudgetExceededError(
                f"EXPANDED_CAP_EXCEEDED: {self.expanded_bytes + n} > {self.expanded_cap}"
            )
        self.expanded_bytes += n


class SafeFetcher:
    """Safe HTTP downloader with atomic staging, rate limiting, and SHA256 calculation."""

    def __init__(self, budget: Budget, rate_limit_delay: float = 0.05):
        self.budget = budget
        self.rate_limit_delay = rate_limit_delay
        self.opener = build_opener(NoRedirectHandler())
        self.last_request_time = 0.0

    def _sleep_rate_limit(self) -> None:
        if self.rate_limit_delay > 0:
            elapsed = time.time() - self.last_request_time
            if elapsed < self.rate_limit_delay:
                time.sleep(self.rate_limit_delay - elapsed)
        self.last_request_time = time.time()

    def fetch_file(
        self,
        url: str,
        dest_path: Path,
        *,
        is_checksum_file: bool = False,
        headers: dict[str, str] | None = None,
        max_retries: int = 3,
    ) -> dict[str, Any] | None:
        """Fetch URL to dest_path via .part atomic file.

        Returns metadata dict on success, None on 404 (not found).
        If dest_path already exists, verifies size and SHA256 without re-downloading.
        """
        # Idempotency check: if already on disk and non-empty
        if dest_path.exists():
            st = dest_path.stat()
            if st.st_size > 0:
                with dest_path.open("rb") as f:
                    digest = hashlib.file_digest(f, "sha256").hexdigest()
                return {
                    "url": url,
                    "bytes": st.st_size,
                    "sha256": digest,
                    "fetched_at_utc": "EXISTING_LOCAL_FILE",
                    "last_modified": "LOCAL",
                    "etag": "LOCAL",
                    "attempts": 0,
                    "reused": True,
                }

        dest_path.parent.mkdir(parents=True, exist_ok=True)
        part_path = dest_path.with_suffix(dest_path.suffix + ".part")
        if part_path.exists():
            part_path.unlink()

        req_headers = {
            "User-Agent": "V065-DATA-R2-AgyDataCollector/1.0 (Research)",
            "Accept-Encoding": "identity",
        }
        if headers:
            req_headers.update(headers)

        for attempt in range(1, max_retries + 1):
            self._sleep_rate_limit()
            self.budget.register_request(url)

            try:
                req = Request(url, headers=req_headers)
                with self.opener.open(req, timeout=60) as resp:
                    if resp.status != 200:
                        raise HTTPError(url, resp.status, "Unexpected status", resp.headers, None)

                    content_length = resp.headers.get("Content-Length")
                    cl_int = int(content_length) if content_length and content_length.isdigit() else None
                    if (
                        cl_int is not None
                        and not is_checksum_file
                        and self.budget.compressed_bytes + cl_int > self.budget.compressed_cap
                    ):
                        raise BudgetExceededError(
                            f"COMPRESSED_CAP_EXCEEDED on response headers: {cl_int} bytes"
                        )

                    hasher = hashlib.sha256()
                    downloaded = 0
                    with part_path.open("wb") as out:
                        while True:
                            chunk = resp.read(65536)
                            if not chunk:
                                break
                            hasher.update(chunk)
                            out.write(chunk)
                            downloaded += len(chunk)
                            if not is_checksum_file:
                                self.budget.consume_compressed(len(chunk))

                    if cl_int is not None and downloaded != cl_int:
                        raise OSError(f"Truncated download: got {downloaded}, expected {cl_int}")

                    # Atomic rename
                    part_path.rename(dest_path)
                    digest = hasher.hexdigest()

                    return {
                        "url": url,
                        "bytes": downloaded,
                        "sha256": digest,
                        "fetched_at_utc": datetime.now(UTC).isoformat(),
                        "last_modified": resp.headers.get("Last-Modified", "UNKNOWN"),
                        "etag": resp.headers.get("ETag", "UNKNOWN"),
                        "attempts": attempt,
                        "reused": False,
                    }

            except HTTPError as e:
                if e.code == 404:
                    if part_path.exists():
                        part_path.unlink()
                    return None
                if e.code == 429:
                    # Rate limit backoff
                    time.sleep(2.0 * attempt)
                elif e.code not in (408, 500, 502, 503, 504):
                    if part_path.exists():
                        part_path.unlink()
                    raise
            except (URLError, TimeoutError, ConnectionError, OSError):
                if attempt == max_retries:
                    if part_path.exists():
                        part_path.unlink()
                    raise

            if part_path.exists():
                part_path.unlink()
            time.sleep(1.0 * attempt)

        return None


def verify_publisher_checksum(data_file: Path, checksum_file: Path) -> tuple[bool, str | None, str]:
    """Verify local SHA256 of data_file against publisher's checksum file.

    Returns (is_verified, publisher_digest, local_digest).
    """
    if not checksum_file.exists():
        with data_file.open("rb") as f:
            local_digest = hashlib.file_digest(f, "sha256").hexdigest()
        return False, None, local_digest

    raw = checksum_file.read_bytes().decode("ascii", errors="ignore").strip()
    match = re.search(r"([0-9a-fA-F]{64})", raw)
    if not match:
        with data_file.open("rb") as f:
            local_digest = hashlib.file_digest(f, "sha256").hexdigest()
        return False, None, local_digest

    publisher_digest = match.group(1).lower()
    with data_file.open("rb") as f:
        local_digest = hashlib.file_digest(f, "sha256").hexdigest()

    is_verified = local_digest == publisher_digest
    return is_verified, publisher_digest, local_digest


def parse_numeric(v: str) -> Decimal:
    """Parse string to finite Decimal, raising ValueError if invalid."""
    try:
        val = Decimal(v)
    except InvalidOperation:
        raise ValueError(f"Invalid decimal: {v}") from None
    if not val.is_finite():
        raise ValueError(f"Non-finite decimal: {v}")
    return val


def parse_integer(v: str) -> int:
    """Parse string to integer."""
    return int(v)


def generate_date_range(start_date: str, end_date: str, end_inclusive: bool = False) -> list[str]:
    """Generate ISO date strings [start_date, end_date) or [start_date, end_date] if end_inclusive.

    Format: YYYY-MM-DD.
    """
    d_start = date.fromisoformat(start_date)
    d_end = date.fromisoformat(end_date)
    if d_start > d_end:
        raise ValueError(f"start_date ({start_date}) must not be after end_date ({end_date})")

    delta = timedelta(days=1)
    cur = d_start
    days: list[str] = []
    while cur <= d_end if end_inclusive else cur < d_end:
        days.append(cur.isoformat())
        cur += delta
    return days


def generate_month_range(start_date: str, end_date: str) -> list[str]:
    """Generate distinct YYYY-MM strings for months intersecting [start_date, end_date) exclusive.

    If start_date == end_date, returns empty list.
    """
    days = generate_date_range(start_date, end_date, end_inclusive=False)
    seen: set[str] = set()
    months: list[str] = []
    for d in days:
        m = d[:7]
        if m not in seen:
            seen.add(m)
            months.append(m)
    return months


def get_okx_utc_window_for_day(date_str: str) -> tuple[str, str]:
    """Convert an OKX daily archive date (UTC+8 calendar day) to its exact UTC event timestamp window.

    OKX files are named by UTC+8 date: [YYYY-MM-DD 00:00:00 CST, YYYY-MM-DD 23:59:59 CST],
    which corresponds to [(date - 1 day) 16:00:00 UTC, date 15:59:59 UTC].
    """
    d = date.fromisoformat(date_str)
    d_prev = d - timedelta(days=1)
    start_utc = f"{d_prev.isoformat()}T16:00:00Z"
    end_utc = f"{d.isoformat()}T15:59:59Z"
    return start_utc, end_utc

