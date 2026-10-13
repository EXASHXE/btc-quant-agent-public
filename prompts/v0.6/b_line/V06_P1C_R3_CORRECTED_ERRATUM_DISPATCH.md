# Controller Dispatch: P1C R3 Repaired H18 Erratum (Docs-Only)

**Task:** `V06_P1C_R3_CORRECTED_H18_ERRATUM`
**Owner:** ChatGPT-0 B-line Controller. **Executor:** Gemini NORMAL. **Independent second reviewer:** Codex Sol/ChatGPT-1 separate from original executor.
**Authority:** this exact prompt's immutable commit SHA, not a moving docs-branch HEAD. Clone a separate docs worktree from that exact SHA; create `docs/v06-p1c-h18-erratum-r3-correction` (no force push).
**Review-fail source:** Controller adjudication `reviews/v0.6/b_line/V06_P1C_H18_INDEPENDENT_REVIEW_FAIL_CONTROLLER_ADJUDICATION_R1.md` in this task commit.

### Read-only fixed sources
- R2 erratum + R2 JSON: `b4f24c763895c97a0c304dc422db76a73761251d`.
- H18 original report + summary: `397a62c1a0fbd6ad14a569a5be0058b1f684f08e`.
- Exit R1 summary + report: `55ac4c631c69f6edbd275462ad23e4486b9782ed`.
- Exact Controller correction table and eight independent-review findings accompanying this prompt.
Do not fetch, read or execute historical raw event files, price returns, trading runners, protected H39/H40/H41/Forward/Final Holdout, private/owner data, Quant-agent-sanitized, accounts, secrets or exchange endpoints.

### Exact write allowlist (NEW documents only)
- `reviews/v0.6/b_line/V06_P1C_H18_TABLE4_CORRECTED_ERRATUM_R3.md`
- `reviews/v0.6/b_line/evidence/V06_P1C_H18_TABLE4_CORRECTED_CROSSWALK_R3.json`
Never edit original R2, H18, Exit R1, CI, tests, code or adjacent roadmap.

### Must pass all conditions
1. Pin SHA/blob identities and source JSON field paths. Enumerate *42* candidate×year×metric cells: observed original narrative value; original unrounded canonical value; correct display rounded to 2 decimals; deviation with correct units; classification; H18 machine field or explicit null. Deterministically assert **24 differ /18 match** and all 42 human-readable statuses match the new JSON statuses.
2. Render the six corrected table rows verbatim from Controller adjudication; compute each paired H1-E0 from unrounded source before display-rounding. W1 2023=56.88bp and W2 2023=27.39bp must both be flagged incorrect in the original narrative.
3. STRESS44 **44bp** round-trip *assumed research proxy* =24bp fees+8bp spread+12bp slippage. Do not relabel this as measured taker fees; account-return discrepancies use **pp**.
4. Limit cross-source H18/Exit R1 agreement to **six annual counts + six paired annual deltas** at stated 1e-10 numeric tolerance. Other 30 H18 source slots null. Do not assert whole-ledger integrity, all timestamp identities, zero historical defect or independent end-to-end replay.
5. Cohort mismatch (W2 2021/2022 N 14/17 vs 10/21) has UNKNOWN original author/partition cause. Difference cannot identify shifted events; Exit accepted-ID date spans cannot be attributed to H18 accepted IDs or receiver clock.
6. W1 2021 Delta +23.95 narrative vs +2.9443 machine, and H1 128.53 vs 107.5206 are factual numeric differences. E2 SHORT scalar≈23.950589 and 104.58+23.95=128.53 do NOT prove the author copied a value: manuscript cause UNKNOWN.
7. Adverse 12-18h continuation 26/56=46.43% is DESCRIPTIVE_ONLY; no inference about 50/50, lack of edge or statistical significance. Four W1/three W2 right-tail target winners are ex-post attribution only, not an ex-ante trade signal.
8. Record R2 REVIEW_FAIL, the independent reviewer objections and R3 dispositions, remaining unknowns and no Alpha/testing permissions. Independent SECOND reviewer must verify all 42 rows and claim scope; mark REVIEW_PENDING unless substantive separate verdict is obtained.

### CI, delivery and hard stops
Docs-only: never run original historic research code; deterministic arithmetic on already-published summary objects is permitted. Check changed paths against two-path allowlist, note actual CI/skips and inherited H41 Ruff debt without changing that evidence or lint policy. Push only new R3 sidecars on isolated docs branch and report commit SHA, parent SHA, separate reviewer evidence and terminal `R3_ERRATUM_REVIEW_READY`, `REVIEW_PENDING` or `R3_BLOCKED`. Do not imply Controller acceptance, strategy promotion, TESTNET or LIVE.
