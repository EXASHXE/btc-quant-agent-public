"""Fail-closed, read-only Owner scope validation. Never creates an allowlist.

Schemas: exposed_dev_bridge.owner-scope.v1 (inspection only) and v2. The caller must supply an existing
Owner decision with identity/reference/issued_at_utc, exposure EXPOSED_DEV,
development_ranges, confirmed protected_date_exclusions, and sources. Each
source pins quarter/venue/root/manifest_sha256/qc_sha256 and an explicit files
list. Each file pins path/sha256/family/market/symbol/start_utc/end_utc; the date
range is the complete native file calendar window, half open. ZIPs are exhausted
for QC, so authorizing only part of a monthly/daily archive is insufficient.

This validates an explicit document, not the human signer's identity. Protected
date governance cannot be inferred from archive coverage or exposure labels.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scripts.research.cross_venue import normalized_sources as n

from . import checked_path


def _hash(value: Any) -> str:
    n.require(type(value) is str and re.fullmatch("[a-f0-9]{64}", value) is not None,
              "SCOPE_HASH_INVALID")
    return value


def _absolute(value: Any) -> Path:
    n.require(type(value) is str and value.startswith("/") and not value.startswith("//") and "\\" not in value
              and str(Path(value)) == value and ".." not in Path(value).parts,
              "SCOPE_PATH_NOT_CANONICAL")
    return checked_path(Path(value))


def _ranges(value: Any, *, protected: bool = False, hour_aligned: bool = False) -> list[tuple[int, int]]:
    n.require(type(value) is list and 0 < len(value) <= 32, "SCOPE_DATE_RANGES_REQUIRED")
    result = []
    mod = 3600 * n.US if hour_aligned else 86400 * n.US
    for item in value:
        n.require(type(item) is dict, "SCOPE_DATE_RANGE_INVALID")
        left, right = n.utc_us(item.get("start_utc")), n.utc_us(item.get("end_utc"))
        n.require(left < right and left % mod == right % mod == 0,
                  "SCOPE_DATE_RANGE_INVALID")
        if protected:
            n.require(item.get("kind") in ("HOLDOUT", "OOS", "PROTECTED"), "PROTECTED_DATE_KIND_REQUIRED")
        result.append((left, right))
    n.require(len(set(result)) == len(result), "SCOPE_DUPLICATE_DATE_RANGE")
    return sorted(result)


def _inside(left: int, right: int, ranges: list[tuple[int, int]]) -> bool:
    return any(a <= left < right <= b for a, b in ranges)


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with n.published_file(path, 8 * 1024**2) as stream:
        for block in iter(lambda: stream.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_scope(scope_path: Path, *, started_ns: int | None = None) -> dict[str, Any]:
    """Validate all dates/paths/identities before any raw archive is hashed.

    No outcome/panel file is accepted or opened by this API. After the structural
    gate, only the explicitly pinned final metadata and PASS feature ZIPs can be
    read. Even a valid scope does not establish sufficient evaluation coverage.
    """
    started_ns = time.time_ns() if started_ns is None else started_ns
    scope_path = _absolute(str(scope_path))
    with n.published_file(scope_path, 1024**2) as stream:
        import os
        n.require(os.fstat(stream.fileno()).st_mtime_ns <= started_ns, "SCOPE_NOT_PREEXISTING")
        raw = stream.read()
    try:
        doc = json.loads(raw, object_pairs_hook=n._unique, parse_constant=n._bad_constant)
    except (UnicodeError, json.JSONDecodeError):
        raise n.BridgeError("SCOPE_JSON_INVALID") from None
    n.require(type(doc) is dict, "EXPOSED_DEV_NOT_AUTHORIZED")
    schema = doc.get("schema")
    n.require(schema in ("exposed_dev_bridge.owner-scope.v1", "exposed_dev_bridge.owner-scope.v2")
              and doc.get("exposure") == "EXPOSED_DEV", "EXPOSED_DEV_NOT_AUTHORIZED")
    auth = doc.get("authorization")
    n.require(type(auth) is dict and auth.get("role") == "Owner"
              and auth.get("decision") == "AUTHORIZE_EXPOSED_DEV"
              and all(type(auth.get(k)) is str and auth[k].strip() for k in ("owner", "reference")),
              "EXPLICIT_OWNER_AUTHORIZATION_REQUIRED")
    n.require(n.utc_us(auth.get("issued_at_utc")) <= started_ns // 1000, "OWNER_AUTHORIZATION_IN_FUTURE")
    governance = doc.get("governance")
    n.require(type(governance) is dict and governance.get("protected_dates_complete") is True
              and governance.get("holdout_status") == "OWNER_CONFIRMED",
              "GOVERNED_HOLDOUT_DATES_UNRESOLVED")
    protected = _ranges(governance.get("protected_date_exclusions"), protected=True)

    archive_raw = doc.get("archive_ranges")
    origin_raw = doc.get("origin_ranges")
    development_raw = doc.get("development_ranges")

    if archive_raw is not None or schema == "exposed_dev_bridge.owner-scope.v2":
        archive_ranges = _ranges(archive_raw if archive_raw is not None else development_raw, hour_aligned=True)
    else:
        archive_ranges = _ranges(development_raw)

    if origin_raw is not None:
        origin_ranges = _ranges(origin_raw, hour_aligned=True)
        n.require(all(_inside(o[0], o[1], archive_ranges) for o in origin_ranges),
                  "ORIGIN_WINDOW_OUTSIDE_ARCHIVE_ENVELOPE")
        n.require(not any(max(a, c) < min(b, d) for a, b in origin_ranges for c, d in protected),
                  "PROTECTED_DATE_OVERLAP")
    else:
        origin_ranges = archive_ranges

    n.require(not any(max(a, c) < min(b, d) for a, b in archive_ranges for c, d in protected),
              "PROTECTED_DATE_OVERLAP")
    sources = doc.get("sources")
    n.require(type(sources) is list and 0 < len(sources) <= 4, "EXACT_SOURCES_REQUIRED")
    plans, roots, identities, keys = [], set(), set(), set()
    file_count = 0
    for source in sources:
        n.require(type(source) is dict, "SCOPE_SOURCE_INVALID")
        key = source.get("quarter"), source.get("venue")
        n.require(key in n.ROOT_NAMES, "UNSUPPORTED_ROOT_IDENTITY")
        n.require(key not in keys, "ROOT_ALIAS_OR_DUPLICATE")
        keys.add(key)
        root = n.safe_directory(_absolute(source.get("root")))
        info = root.stat()
        identity = info.st_dev, info.st_ino
        n.require(root not in roots and identity not in identities, "ROOT_ALIAS_OR_DUPLICATE")
        roots.add(root)
        identities.add(identity)
        _hash(source.get("manifest_sha256"))
        _hash(source.get("qc_sha256"))
        files = source.get("files")
        n.require(type(files) is list and 0 < len(files) <= 1000, "EXACT_FILES_REQUIRED")
        seen = set()
        for entry in files:
            n.require(type(entry) is dict, "SCOPE_FILE_INVALID")
            relative = entry.get("path")
            n.require(type(relative) is str and "\\" not in relative and str(Path(relative)) == relative
                      and not Path(relative).is_absolute() and ".." not in Path(relative).parts
                      and relative not in seen, "SCOPE_FILE_PATH_INVALID")
            seen.add(relative)
            checked_path(root / relative)
            family, symbol = entry.get("family"), entry.get("symbol")
            n.require(family in n.FEATURE_FAMILIES, "SCOPE_NON_FEATURE_FILE_FORBIDDEN")
            _, market, _ = n.expected_identity(key[1], family, symbol)
            n.require(market == entry.get("market"), "SCOPE_SOURCE_IDENTITY_MISMATCH")
            left, right = n.utc_us(entry.get("start_utc")), n.utc_us(entry.get("end_utc"))
            n.require(_inside(left, right, archive_ranges), "FILE_DATE_OUTSIDE_AUTHORIZED_DEVELOPMENT")
            n.require(not any(max(left, a) < min(right, b) for a, b in protected), "PROTECTED_DATE_OVERLAP")
            _hash(entry.get("sha256"))
        file_count += len(files)
        plans.append((key, root, source))
    n.require(file_count <= 1500, "SCOPE_FILE_LIMIT")

    snapshots, verified = [], []
    try:
        for (quarter, venue), root, plan in plans:
            snap = n.Snapshot.capture(root, venue, quarter)
            snapshots.append(snap)
            n.require(snap.before == {"manifest.json": plan["manifest_sha256"], "qc.json": plan["qc_sha256"]},
                      "SCOPE_METADATA_HASH_MISMATCH")
            # Zero reservation budget: dispatch/validate metadata, never open an
            # unlisted file or a NON_PASS/non-feature archive.
            inventory = n.expansion_sources(snap, n.Budget(expanded_cap=0))
            by_path = {s.record["local_path"]: s for s in inventory}
            for entry in plan["files"]:
                candidate = by_path.get(entry["path"])
                n.require(candidate is not None and candidate.record.get("verdict") == "PASS"
                          and candidate.qc.get("verdict") == "PASS", "SCOPE_FILE_NOT_PASS")
                record = candidate.record
                n.require(all(entry[k] == record[k] for k in ("family", "market", "symbol"))
                          and entry["sha256"] == record["local_sha256"], "SCOPE_FILE_IDENTITY_OR_HASH_MISMATCH")
                window = n.file_window(record, venue)
                n.require(window == (n.utc_us(entry["start_utc"]), n.utc_us(entry["end_utc"])),
                          "FULL_ARCHIVE_DATE_AUTHORIZATION_REQUIRED")
                path = root / entry["path"]
                digest = _digest(path)
                n.require(digest == entry["sha256"], "SCOPE_RAW_HASH_MISMATCH")
                verified.append({"path": str(path), "sha256": digest, "family": record["family"],
                                 "venue": venue, "market": record["market"], "symbol": record["symbol"],
                                 "start_utc_us": window[0], "end_utc_us_exclusive": window[1]})
        # A raw file replaced after an earlier hash must not pass the gate.
        for item in verified:
            try:
                unchanged = _digest(Path(item["path"])) == item["sha256"]
            except (OSError, n.BridgeError):
                unchanged = False
            n.require(unchanged, "INPUT_CHANGED", path=item["path"])
        try:
            scope_unchanged = _digest_scope(scope_path) == hashlib.sha256(raw).hexdigest()
        except (OSError, n.BridgeError):
            scope_unchanged = False
        n.require(scope_unchanged, "INPUT_CHANGED", document="scope")
    finally:
        for snap in snapshots:
            snap.verify()
    embargo_candidates = [c for c, d in protected if c > origin_ranges[0][0]]
    embargo_us = min(embargo_candidates) if embargo_candidates else origin_ranges[-1][1]
    horizon_cutoffs = {h: ((embargo_us - 1) // n.US - 120 - h * 3600) // 3600 * 3600 + 60
                       for h in (8, 4, 12, 24)}
    return {"gate_status": "AUTHORIZED_SCOPE_ONLY", "scope_sha256": hashlib.sha256(raw).hexdigest(),
            "schema": schema,
            "scope_path": str(scope_path), "governance": governance,
            "p1_binding": doc.get("p1_binding"),
            "authorization": "EXPLICIT_OWNER_DOCUMENT_NOT_IDENTITY_ATTESTATION", "owner_reference": auth["reference"],
            "exposure": "EXPOSED_DEV", "development_ranges_utc_us_half_open": origin_ranges,
            "archive_ranges_utc_us_half_open": archive_ranges,
            "origin_ranges_utc_us_half_open": origin_ranges,
            "horizon_origin_cutoffs": horizon_cutoffs,
            "protected_date_exclusions_utc_us_half_open": protected,
            "sources": [s.receipt() for s in snapshots], "verified_files": verified,
            "outcome_labels_read": 0, "historical_outcomes_evaluated": 0}


def _digest_scope(path: Path) -> str:
    with n.published_file(path, 1024**2) as stream:
        return hashlib.sha256(stream.read()).hexdigest()


PRIVATE_PARTITIONS = ("A_LINE", "FINAL_HOLDOUT", "FORWARD", "OOS", "H41")


def _private_dates_confirmed(scope: dict[str, Any]) -> None:
    """Shared pre-label gate for both the legacy and derived-integrity contracts."""
    attestations = scope["governance"].get("private_partition_attestations")
    n.require(type(attestations) is dict and set(attestations) == set(PRIVATE_PARTITIONS),
              "PRIVATE_PROTECTED_PARTITIONS_UNCONFIRMED")
    protected = scope["protected_date_exclusions_utc_us_half_open"]
    for name in PRIVATE_PARTITIONS:
        item = attestations[name]
        n.require(type(item) is dict and item.get("status") == "OWNER_CONFIRMED"
                  and type(item.get("reference")) is str and bool(item["reference"].strip())
                  and type(item.get("date_exclusions")) is list,
                  "PRIVATE_PROTECTED_PARTITIONS_UNCONFIRMED", partition=name)
        if item["date_exclusions"]:
            ranges = _ranges(item["date_exclusions"], protected=True)
            n.require(all(_inside(a, b, protected) for a, b in ranges),
                      "PRIVATE_PARTITION_NOT_EXCLUDED", partition=name)
    known = [(n.utc_us("2025-02-01T00:00:00Z"), n.utc_us("2026-02-01T00:00:00Z")),
             (n.utc_us("2026-09-01T00:00:00Z"), n.utc_us("2026-10-01T00:00:00Z"))]
    archive = scope["archive_ranges_utc_us_half_open"]
    n.require(not any(max(a, c) < min(b, d) for a, b in archive for c, d in known),
              "PROTECTED_DATE_OVERLAP")


@dataclass(frozen=True)
class PhaseOnePermit:
    """Owner permission for bounded panel materialization, never P1 evaluation."""
    scope_path: Path
    panel_path: Path
    allowlist_path: Path
    scope_sha256: str
    start: int
    end: int
    scope: dict[str, Any]

    def verify(self) -> None:
        n.require(_digest_scope(self.scope_path) == self.scope_sha256,
                  "INPUT_CHANGED", document="owner_scope")


def authorize_phase_one(scope_path: Path, panel_path: Path, *, started_ns: int | None = None) -> PhaseOnePermit:
    """Require explicit Owner materialization permission before any outcome row."""
    scope = validate_scope(scope_path, started_ns=started_ns)
    n.require(scope["schema"] == "exposed_dev_bridge.owner-scope.v2", "OWNER_SCOPE_V2_REQUIRED")
    _private_dates_confirmed(scope)
    with n.published_file(_absolute(str(scope_path)), 1024**2) as stream:
        document = json.loads(stream.read(), object_pairs_hook=n._unique, parse_constant=n._bad_constant)
    auth = document["authorization"]
    n.require(auth.get("outcome_panel_materialization") == "AUTHORIZE_EXPOSED_DEV_PANEL_MATERIALIZATION",
              "OWNER_PANEL_MATERIALIZATION_PERMISSION_REQUIRED")
    binding = scope.get("p1_binding")
    n.require(type(binding) is dict and binding.get("mode") == "DERIVED_P1_INTEGRITY_V1",
              "OWNER_DERIVED_BINDING_REQUIRED")
    panel_path = _absolute(str(panel_path))
    allowlist_path = _absolute(str(binding.get("allowlist_path")))
    from scripts.research.strategy_eval import DAY, clocked_dataset as p1
    p1.safe_directory(panel_path.parent, missing=True)
    n.require(panel_path.is_relative_to(Path("/tmp")) and panel_path.name == "normalized_panel.json"
              and not panel_path.exists(), "FRESH_TMP_PANEL_REQUIRED")
    n.require(binding.get("panel_path") == str(panel_path)
              and allowlist_path == panel_path.with_name("p1_integrity_allowlist.json")
              and not allowlist_path.exists(), "OWNER_P1_PATH_BINDING_MISMATCH")
    n.require("panel_sha256" not in binding and "allowlist_sha256" not in binding,
              "DERIVED_HASH_MUST_NOT_BE_PREAUTHORIZED")
    start, end = binding.get("start_utc_s"), binding.get("end_utc_s")
    n.require(type(start) is int and type(end) is int and start % DAY == end % DAY == 0
              and 0 < end - start <= 92 * DAY, "P1_BOUND_INTERVAL_INVALID")
    n.require(_inside(start * n.US, end * n.US, scope["origin_ranges_utc_us_half_open"]),
              "P1_INTERVAL_OUTSIDE_OWNER_ORIGINS")
    n.require(end * n.US <= min(n.utc_us("2026-09-01T00:00:00Z"),
                               scope["archive_ranges_utc_us_half_open"][-1][1]),
              "PROTECTED_DATE_OVERLAP")
    n.require(_digest_scope(_absolute(str(scope_path))) == scope["scope_sha256"],
              "INPUT_CHANGED", document="owner_scope")
    return PhaseOnePermit(_absolute(str(scope_path)), panel_path, allowlist_path,
                          scope["scope_sha256"], start, end, scope)


@dataclass(frozen=True)
class DualGate:
    """An existing Owner scope binds an independently existing P1 allowlist.

    No caller flag creates this permit. Expected panel bytes are pinned before
    any label-bearing source is opened and checked again before P1 delegation.
    """
    scope_path: Path
    allowlist_path: Path
    panel_path: Path
    scope_sha256: str
    allowlist_sha256: str
    panel_sha256: str
    start: int
    end: int
    scope: dict[str, Any]

    def verify(self) -> None:
        n.require(_digest_scope(self.scope_path) == self.scope_sha256
                  and _digest_scope(self.allowlist_path) == self.allowlist_sha256,
                  "INPUT_CHANGED", document="dual_authority")


def _preexisting_json(path: Path, started_ns: int) -> tuple[dict[str, Any], str]:
    import os
    path = _absolute(str(path))
    with n.published_file(path, 1024**2) as stream:
        n.require(os.fstat(stream.fileno()).st_mtime_ns <= started_ns, "P1_ALLOWLIST_NOT_PREEXISTING")
        raw = stream.read()
    doc = json.loads(raw, object_pairs_hook=n._unique, parse_constant=n._bad_constant)
    n.require(type(doc) is dict, "P1_ALLOWLIST_SCHEMA_INVALID")
    return doc, hashlib.sha256(raw).hexdigest()


def authorize_dual_gate(scope_path: Path, allowlist_path: Path | None,
                        panel_path: Path, *, started_ns: int | None = None) -> DualGate:
    """Reject incomplete authority before any CSV price/funding label read.

    Each private partition needs an explicit Owner-confirmed reference and a
    date_exclusions list (empty means Owner reviewed it and found no excluded
    dates). Nonempty dates must also occur in the main protected exclusions.
    p1_binding is part of the original Owner document, never authored here.
    """
    started_ns = time.time_ns() if started_ns is None else started_ns
    scope = validate_scope(scope_path, started_ns=started_ns)
    n.require(scope["schema"] == "exposed_dev_bridge.owner-scope.v2", "OWNER_SCOPE_V2_REQUIRED")
    _private_dates_confirmed(scope)
    n.require(allowlist_path is not None, "P1_ALLOWLIST_REQUIRED")
    binding = scope.get("p1_binding")
    n.require(type(binding) is dict, "OWNER_P1_BINDING_REQUIRED")
    panel_path, allowlist_path = _absolute(str(panel_path)), _absolute(str(allowlist_path))
    from scripts.research.strategy_eval import DAY, clocked_dataset as p1
    p1.safe_directory(panel_path.parent, missing=True)
    n.require(panel_path.is_relative_to(Path("/tmp")) and not panel_path.exists(),
              "FRESH_TMP_PANEL_REQUIRED")
    n.require(binding.get("panel_path") == str(panel_path)
              and binding.get("allowlist_path") == str(allowlist_path), "OWNER_P1_PATH_BINDING_MISMATCH")
    expected_sha, expected_allowlist_sha = _hash(binding.get("panel_sha256")), _hash(binding.get("allowlist_sha256"))
    start, end = binding.get("start_utc_s"), binding.get("end_utc_s")
    n.require(type(start) is int and type(end) is int and start % DAY == end % DAY == 0
              and 0 < end - start <= 92 * DAY, "P1_BOUND_INTERVAL_INVALID")
    n.require(_inside(start * n.US, end * n.US, scope["origin_ranges_utc_us_half_open"]),
              "P1_INTERVAL_OUTSIDE_OWNER_ORIGINS")
    doc, actual_sha = _preexisting_json(allowlist_path, started_ns)
    n.require(actual_sha == expected_allowlist_sha, "P1_ALLOWLIST_HASH_MISMATCH")
    n.require(doc.get("schema") == "strategy_eval.exposed-dev.v1" and doc.get("exposure") == "EXPOSED_DEV"
              and type(doc.get("panels")) is list, "P1_ALLOWLIST_SCHEMA_INVALID")
    n.require(not doc.get("test_only") and doc.get("data_kind") != "TEST_ONLY_SYNTHETIC",
              "SYNTHETIC_ALLOWLIST_FOR_REAL_INPUT_FORBIDDEN")
    entries = [e for e in doc["panels"] if type(e) is dict and e.get("path") == str(panel_path)]
    n.require(len(entries) == 1 and entries[0].get("sha256") == expected_sha
              and type(entries[0].get("start_utc_s")) is int and entries[0]["start_utc_s"] == start
              and type(entries[0].get("end_utc_s")) is int and entries[0]["end_utc_s"] == end,
              "P1_PANEL_BINDING_MISMATCH")
    permit = DualGate(_absolute(str(scope_path)), allowlist_path, panel_path,
                      scope["scope_sha256"], actual_sha, expected_sha, start, end, scope)
    permit.verify()
    return permit


