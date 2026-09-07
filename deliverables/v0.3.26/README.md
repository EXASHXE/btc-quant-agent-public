# BTC Quant Agent v0.3.26 Deliverables

This release is a narrow H39 scientific-validity and blind-input repair. It does not add or search for alpha.

- `H39_PROTOCOL_CLARIFICATION_004_CONDITIONAL_INPUT_CONTRACT.json` freezes the corrected future protocol identity.
- The corrected evaluator is `H39_CONDITIONAL_OLS_HAC_V1`.
- The label-free maturity contract is `H39_REQUIRED_INPUT_V1`.
- Historical v0.3.22-v0.3.25 artifacts and legacy evaluator code remain unchanged for reproduction.
- `reviews/v0.3.26/H39_BLOCKER_FIX_REVIEW.md` records causes, repairs, synthetic counterexamples, verification, compatibility, and remaining risks.

Safety state remains `EXPERIMENTAL / NONE / OPPORTUNITY_ONLY / DISABLED`, with Final Holdout sealed.
