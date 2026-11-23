"""Strict zero-dependency JSON and YAML-1.2 safe subset loader for versioned configs."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .models import OptionalRiskConfigError, scan_forbidden_live_or_secret_fields

MAX_CONFIG_BYTES = 262_144
_INT_RE = re.compile(r"^[+-]?\d+$")
_UNQUOTED_FLOAT_OR_EXP_RE = re.compile(r"^[+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?$")


def _reject_duplicate_json_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in pairs:
        if k in out:
            raise OptionalRiskConfigError("DUPLICATE_CONFIG_KEY", k)
        out[k] = v
    return out


def _reject_json_float(raw: str) -> Any:
    raise OptionalRiskConfigError("BINARY_FLOAT_FORBIDDEN", raw)


def _reject_json_constant(raw: str) -> Any:
    raise OptionalRiskConfigError("NON_FINITE_OR_INVALID_CONSTANT", raw)


def _strip_yaml_comment(line: str) -> str:
    quote: str | None = None
    escaped = False
    for idx, ch in enumerate(line):
        if escaped:
            escaped = False
            continue
        if quote is not None:
            if quote == '"' and ch == "\\":
                escaped = True
            elif ch == quote:
                quote = None
            continue
        if ch in ('"', "'"):
            quote = ch
        elif ch == "#" and (idx == 0 or line[idx - 1].isspace()):
            return line[:idx].rstrip()
    if quote is not None:
        raise OptionalRiskConfigError("UNTERMINATED_QUOTED_STRING")
    return line.rstrip()


def _parse_yaml_scalar(token: str) -> Any:
    text = token.strip()
    if not text:
        raise OptionalRiskConfigError("EMPTY_YAML_SCALAR")
    if text[0] in ("&", "*", "!", "%") or text in ("|", ">", "|-", ">-"):
        raise OptionalRiskConfigError("UNSUPPORTED_YAML_CONSTRUCT", text[:20])
    if text.startswith("[") and text.endswith("]"):
        inner = text[1:-1].strip()
        if not inner:
            return []
        items: list[Any] = []
        buf: list[str] = []
        quote: str | None = None
        escaped = False
        for ch in inner:
            if escaped:
                buf.append(ch)
                escaped = False
                continue
            if quote is not None:
                buf.append(ch)
                if quote == '"' and ch == "\\":
                    escaped = True
                elif ch == quote:
                    quote = None
                continue
            if ch in ('"', "'"):
                quote = ch
                buf.append(ch)
            elif ch == ",":
                items.append(_parse_yaml_scalar("".join(buf)))
                buf = []
            else:
                buf.append(ch)
        if quote is not None:
            raise OptionalRiskConfigError("UNTERMINATED_INLINE_LIST_STRING")
        items.append(_parse_yaml_scalar("".join(buf)))
        return items
    if text.startswith("{") or text.startswith("["):
        raise OptionalRiskConfigError("UNSUPPORTED_INLINE_COLLECTION", text[:20])
    if text.startswith('"') and text.endswith('"') and len(text) >= 2:
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise OptionalRiskConfigError("INVALID_DOUBLE_QUOTED_STRING") from exc
    if text.startswith("'") and text.endswith("'") and len(text) >= 2:
        return text[1:-1].replace("''", "'")
    low = text.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    if low in ("null", "~"):
        return None
    if low in (".nan", ".inf", "-.inf", "+.inf", "nan", "inf", "-inf"):
        raise OptionalRiskConfigError("NON_FINITE_YAML_LITERAL", text)
    if _INT_RE.fullmatch(text):
        return int(text)
    if _UNQUOTED_FLOAT_OR_EXP_RE.fullmatch(text):
        raise OptionalRiskConfigError("BINARY_FLOAT_FORBIDDEN", text)
    return text


def _split_yaml_key_value(body: str) -> tuple[str, str]:
    quote: str | None = None
    escaped = False
    for idx, ch in enumerate(body):
        if escaped:
            escaped = False
            continue
        if quote is not None:
            if quote == '"' and ch == "\\":
                escaped = True
            elif ch == quote:
                quote = None
            continue
        if ch in ('"', "'"):
            quote = ch
        elif ch == ":" and (idx + 1 == len(body) or body[idx + 1] == " "):
            key_raw = body[:idx].strip()
            val_raw = body[idx + 1 :].strip()
            if not key_raw or key_raw == "<<":
                raise OptionalRiskConfigError("UNSUPPORTED_OR_EMPTY_YAML_KEY", key_raw)
            key = _parse_yaml_scalar(key_raw)
            if not isinstance(key, str) or not key:
                raise OptionalRiskConfigError("NON_STRING_YAML_KEY", key_raw)
            return key, val_raw
    raise OptionalRiskConfigError("INVALID_YAML_MAPPING_LINE", body[:40])


def parse_strict_yaml_mapping(text: str) -> dict[str, Any]:
    """Parse a strict, flat-or-nested YAML-1.2 subset into a dict without binary floats."""
    tokens: list[tuple[int, int, str]] = []
    for lineno, raw_line in enumerate(text.splitlines(), 1):
        if "\t" in raw_line:
            raise OptionalRiskConfigError("YAML_TABS_FORBIDDEN", f"line {lineno}")
        stripped = _strip_yaml_comment(raw_line)
        if not stripped:
            continue
        if stripped in ("---", "..."):
            if tokens:
                raise OptionalRiskConfigError("MULTI_DOCUMENT_YAML_FORBIDDEN", f"line {lineno}")
            continue
        indent = len(stripped) - len(stripped.lstrip(" "))
        tokens.append((lineno, indent, stripped.lstrip(" ")))

    if not tokens:
        raise OptionalRiskConfigError("EMPTY_CONFIG_DOCUMENT")

    def parse_block(idx: int, expected_indent: int) -> tuple[Any, int]:
        if idx >= len(tokens):
            raise OptionalRiskConfigError("UNEXPECTED_EOF_IN_YAML")
        _, indent, first = tokens[idx]
        if indent != expected_indent:
            raise OptionalRiskConfigError("INVALID_YAML_INDENTATION", f"line {tokens[idx][0]}")
        if first == "-" or first.startswith("- "):
            seq: list[Any] = []
            while idx < len(tokens) and tokens[idx][1] == expected_indent:
                lineno, _, item = tokens[idx]
                if item == "-":
                    idx += 1
                    if idx >= len(tokens) or tokens[idx][1] <= expected_indent:
                        raise OptionalRiskConfigError("EMPTY_YAML_LIST_ITEM", f"line {lineno}")
                    child, idx = parse_block(idx, tokens[idx][1])
                    seq.append(child)
                elif item.startswith("- "):
                    rest = item[2:].strip()
                    seq.append(_parse_yaml_scalar(rest))
                    idx += 1
                else:
                    raise OptionalRiskConfigError("MIXED_YAML_SEQUENCE_MAPPING", f"line {lineno}")
            return seq, idx

        mapping: dict[str, Any] = {}
        while idx < len(tokens) and tokens[idx][1] == expected_indent:
            lineno, _, item = tokens[idx]
            if item == "-" or item.startswith("- "):
                raise OptionalRiskConfigError("MIXED_YAML_MAPPING_SEQUENCE", f"line {lineno}")
            key, rest = _split_yaml_key_value(item)
            if key in mapping:
                raise OptionalRiskConfigError("DUPLICATE_CONFIG_KEY", key)
            idx += 1
            if rest:
                mapping[key] = _parse_yaml_scalar(rest)
            else:
                if idx < len(tokens) and tokens[idx][1] > expected_indent:
                    child, idx = parse_block(idx, tokens[idx][1])
                    mapping[key] = child
                else:
                    raise OptionalRiskConfigError("EMPTY_YAML_BLOCK_VALUE", f"{key} line {lineno}")
        return mapping, idx

    result, end_idx = parse_block(0, tokens[0][1])
    if end_idx != len(tokens) or not isinstance(result, dict):
        raise OptionalRiskConfigError("INVALID_TOP_LEVEL_YAML_OBJECT")
    return result


def load_structured_file(path: Path) -> dict[str, Any]:
    """Read and strictly parse a regular non-symlink JSON or YAML file."""
    resolved = path.resolve()
    if path.is_symlink() or resolved.is_symlink():
        raise OptionalRiskConfigError("SYMLINK_CONFIG_FORBIDDEN", str(path))
    if not resolved.is_file():
        raise OptionalRiskConfigError("CONFIG_FILE_MISSING", str(path))
    if resolved.stat().st_size > MAX_CONFIG_BYTES:
        raise OptionalRiskConfigError("CONFIG_FILE_TOO_LARGE", str(path))
    raw_text = resolved.read_text(encoding="utf-8")
    suffix = resolved.suffix.lower()
    if suffix == ".json":
        try:
            loaded = json.loads(
                raw_text,
                object_pairs_hook=_reject_duplicate_json_pairs,
                parse_float=_reject_json_float,
                parse_constant=_reject_json_constant,
            )
        except json.JSONDecodeError as exc:
            raise OptionalRiskConfigError("MALFORMED_JSON_CONFIG", str(exc)) from exc
        if not isinstance(loaded, dict):
            raise OptionalRiskConfigError("CONFIG_MUST_BE_MAPPING")
    elif suffix in (".yaml", ".yml"):
        loaded = parse_strict_yaml_mapping(raw_text)
    else:
        raise OptionalRiskConfigError("UNSUPPORTED_CONFIG_EXTENSION", suffix)
    scan_forbidden_live_or_secret_fields(loaded)
    return loaded
