from __future__ import annotations

from pathlib import Path


path = Path("src/btc_quant_agent/research_contract/registry.py")
text = path.read_text(encoding="utf-8")
old = 'P6_RESULT_SCHEMA_VERSION = "1.0.0"\n'
new = 'P6_RESULT_SCHEMA_VERSION = "1.1.0"\n'
if old not in text:
    raise RuntimeError("expected registry P6 schema anchor missing")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
