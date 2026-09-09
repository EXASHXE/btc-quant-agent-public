from __future__ import annotations

from pathlib import Path


path = Path("src/btc_quant_agent/research_contract/models.py")
text = path.read_text(encoding="utf-8")
old = '        if self.result_schema_version != "1.0.0":\n            raise ValueError("unsupported economic result schema")\n'
new = (
    '        if self.result_schema_version not in {"1.0.0", "1.1.0"}:\n'
    '            raise ValueError("unsupported economic result schema")\n'
)
if old not in text:
    raise RuntimeError("expected economic attestation schema anchor missing")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
