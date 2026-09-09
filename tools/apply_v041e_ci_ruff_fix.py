from __future__ import annotations

from pathlib import Path


PATH = Path("src/btc_quant_agent/economic/acceptance_verifier.py")
text = PATH.read_text(encoding="utf-8")
replacements = (
    (
        'raise ValueError("formal dataset evidence must be a canonical candle array")',
        'raise TypeError("formal dataset evidence must be a canonical candle array")',
    ),
    (
        'raise ValueError(f"dataset candle {index} must be a JSON object")',
        'raise TypeError(f"dataset candle {index} must be a JSON object")',
    ),
    (
        'raise ValueError(f"{label} must be a JSON object")',
        'raise TypeError(f"{label} must be a JSON object")',
    ),
    (
        'raise ValueError(f"{label} must be a JSON array")',
        'raise TypeError(f"{label} must be a JSON array")',
    ),
    (
        'raise ValueError(f"{label} must be numeric")',
        'raise TypeError(f"{label} must be numeric")',
    ),
)
for old, new in replacements:
    if old not in text:
        raise RuntimeError(f"expected ruff-fix anchor missing: {old}")
    text = text.replace(old, new)
PATH.write_text(text, encoding="utf-8")
