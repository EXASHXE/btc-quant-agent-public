# QUANT v0.8.0 — Personal Trading Decision Support

Local working root: \`/root/workspace/project/quant-0.8.0/\`

Read first:
- \`docs/project/V080_PROJECT_HOME_20261118.md\`
- \`docs/project/V080_OWNER_REBASELINE_DECISION_20261118.md\`
- \`docs/architecture/V080_THREE_LAYER_API_ARCHITECTURE_20261118.md\`

This is a new personal-use 2–12h Binance USDⓈ-M decision-support baseline. It has three separate layers: public market GET, optional private USER_DATA signed GET, and disabled TRADE_EXECUTION.

The Owner's 2026-10-24 standing public-data attestation is copied byte-identically and reused as OWNER_ATTESTED; it must not be requested again for the same scope. Private API credentials remain local and are never supplied to a model. TRADE remains disabled.

\`baseline/program-j/\` is a read-only source snapshot. All new local tasks and isolated workspaces belong under this project root. The R1 task prompt is pending Controller 0-C review, not yet dispatched.
