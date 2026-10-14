# Independent review task — BTC Intraday Alpha Discovery

You are an independent adversarial quantitative researcher. Read the branch-local files in [the root README](../../README.md) and the source provenance [manifest](FILE_MANIFEST.md). Every material numerical assertion must specify its exact reviewed path and scope. Do not infer that cached context or a GitHub URL not actually fetched has been verified.

Assess two proposed **hypotheses, not approved trading strategies**:
1. **Price shock + Open Interest contraction / possible reversal** (OI alone does not prove forced liquidation).
2. **Spot-led vs perp-led flow divergence / continuation** (single-venue spot CVD does not prove institutional accumulation).

Evaluate (a) economic counterparty mechanism, (b) difference from R3/Goal-A/Goal-B, (c) historical/prospective PIT data availability especially OI 5m and Spot CVD, (d) event occurrence frequency around 0.5 valid portfolio events/day, (e) fees, bid/ask, execution/nonfill/slippage and signed Funding, (f) matched price/vol-only baselines and feature ablation, (g) sparse/event-cluster inference and multiplicity, (h) failure modes and irreducible unknowns.

**Deliver:** evidence-backed diagnosis; two minimal falsifiable designs; source/permission gap matrix; explicit realistic/unknown cost scenarios; a finite outcome-blind study to identify whether a later prospective G2 test is justified; three priorities for Controller. Separate facts from hypotheses and cite branch-local paths.

**Do not:** access protected H39/H40/H41/Forward/Final Holdout/owner data or private accounts; write code, run backtests, alter frozen outcomes, access live market endpoints, place orders or assert independent Alpha without a separate exact-SHA Controller authorization. Reply to the user in Chinese; any repository reports or delegated prompts in English.
