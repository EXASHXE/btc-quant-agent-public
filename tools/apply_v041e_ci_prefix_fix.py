from __future__ import annotations

from pathlib import Path


path = Path("src/btc_quant_agent/economic/acceptance_verifier.py")
text = path.read_text(encoding="utf-8")
old = "        count, portfolio, equity = matches[0]\n"
new = (
    "        # Multiple same-timestamp prefixes can mark to the same equity (for example,\n"
    "        # a zero-cost close filled at the candle close).  The simulator records its\n"
    "        # close mark after all close-time ledger effects, so prefer the latest\n"
    "        # reconstructable prefix rather than silently treating a completed exit as\n"
    "        # still open.  Prefixes that include a next-bar event at the same timestamp\n"
    "        # remain excluded when they change the observed close equity.\n"
    "        count, portfolio, equity = matches[-1]\n"
)
if old not in text:
    raise RuntimeError("expected replay-prefix anchor missing")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
