# V065-M5 — Controller Frozen 42-ref Reconciliation and Parallel Dispatch R1

**Controller disposition:** `M5_DISPATCH_PUBLISHED__ROLE_RELEASE_PENDING`. This is a NON-DESTRUCTIVE governance dispatch only, not a released-ref or actual branch-deletion receipt. Date: 2026-10-17. Research home remains `v0.6.5`; engineering maintenance documentation home is `docs/engineering`. No active science/release gate changes.

## Immutable authorities

Frozen M4: https://github.com/EXASHXE/btc-quant-agent-public/blob/41e49989745294cc05c811cda16805dd419b63e6/repository-maintenance/v065-m4/RELEASE_REGISTER.json
Owner receipt: https://github.com/EXASHXE/btc-quant-agent-public/blob/84955be4cd947cf6a92a9e09c036daf4b948f3fb/repository-maintenance/v065-m4/V065_M4_OWNER_BATCH_REFERENCE_RETIREMENT_DECISION_RECEIPT_R1.md
1-A R2: https://github.com/EXASHXE/btc-quant-agent-public/blob/d427c34a73628e66ae362851bdacad89968155f0/repository-maintenance/v065-m4/INDEPENDENT_1A_REFERENCE_RETIREMENT_RELEASE_REVIEW_R2.json

Exact anchors: M4 commit `41e49989745294cc05c811cda16805dd419b63e6` / register blob `8be7b7efdbc3ef1ab8af3212147c89c66ce00e39`; Owner receipt commit `84955be4cd947cf6a92a9e09c036daf4b948f3fb`; 1-A R2 commit `d427c34a73628e66ae362851bdacad89968155f0` / blob `81c351d88899d4efb13e4a9e51e0d12bee12e1f3`.

Observed now: GitHub default `v0.6.5` @ `275bb5fc71fa21944375d8118945a6074030353e`; `docs/engineering` parent `d427c34a73628e66ae362851bdacad89968155f0`; legacy `0176cdde836a660420e5e4b5693591cb8108a4f6`. REST branches per_page=100 returns 49 refs; exact M4 42/42 named SHA refs match current remote, 3 long-term and 4 live PR-dependency refs preserved. PR #3/#5 are OPEN/DRAFT. If refs change at any later decision, reverify them.

M4 register blob exactly `8be7b7efdbc3ef1ab8af3212147c89c66ce00e39` and R2 blob exactly `81c351d88899d4efb13e4a9e51e0d12bee12e1f3`; M4/R2 both report **0 RELEASE_READY / 42 HOLD**. Owner's exact 42-ref ref-only authorization is present, does not confer A-line controller or protected evidence stewardship release. Class split: A-line 26, former-default-and-A-line 1; protected-control 15. M4 42/42 previous private restoration PASS, 11 already public legacy ancestors, **31 private-only**, new public graph extension forbidden. Two durable physical copies previously attested, but independent host-failure domain and extra encrypted offsite proof NOT established; fresh deletion-time backups must be proven separately.

## Parallel-first tasks / authority and status

- **M5-A** exact 27 refs. Existing independent A-line Scientific Controller in a separate A-line chat. **READY_TO_DISPATCH**, requires genuine A-line role authority. Task: `V065_M5_A_A_LINE_SCIENTIFIC_CONTROLLER_27_REF_RELEASE_PROMPT_R1.md`. May yield mixed individual REF_RETIREMENT_APPROVED/HOLD; no science rerun.
- **M5-B** exact 15 refs. Control/Evidence Steward independent of Controller/1-A. **DESIGNATION_PENDING**; reviewed R2, M4 and existing role contracts contain no independently named/applicable steward appointment. Publish prompt now to run in parallel once owner supplies actual steward identity/mandate, not to fabricate a signature: `V065_M5_B_CONTROL_EVIDENCE_STEWARD_15_REF_RELEASE_PROMPT_R1.md`. A designation itself does not approve 15 refs.
- **M5-1A FINAL** one independent register across 42. **NOT_AUTHORIZED_TO_EXECUTE** until authentic attributable role-specific M5-A & M5-B decision receipts are remotely frozen and independently identifiable: `V065_M5_1A_FINAL_42_REF_RELEASE_REGISTER_CONDITIONAL_PROMPT_R1.md`.

## Minimal missing owner decision (not retirement reauthorization)

**Owner need only identify/designate the actual independent Control/Evidence Steward** with scoped one-time H40/holdout/Forward historical-evidence custody authority for the 15 M4 frozen control refs (by identifiable separate person/role and explicit independence). The M5-B prompt contains an exact narrow appointment sentence. Do not replace designation with GitHub admin, ChatGPT-0, or 1-A's final independent review. If nobody is eligible, HOLD 15 and ask the owner to appoint an actual separate reviewer; do not manufacture one.

## Dependency DAG

```text
M4 + Owner authorization + independent 1-A R2
                    |
          Controller M5 dispatch
            /              \
M5-A: A-line 27       M5-B: steward 15
READY                  DESIG. PENDING
            \              /
    Exact-SHA role authority / batch receipts
                    |
          1-A final 42-ref register
        (CONDITIONAL, NOT ACTIVATED)
                    |
       Separate deletion-time preflight
     (NOT PART OF M5; NO PERMISSION)
```

## Completion, STOP and fences

M5-A and M5-B must each enumerate every frozen pair with individual approval or HOLD, signed/attested by a genuinely authorized role, with original evidence preservation and no new public ancestry. 1-A independently checks all 42, writes a *new* release register with RELEASE_READY only when applicable role's positive grant is verified, else HOLD. STOP on missing steward designation, missing A-line authority, altered/missing SHA, privacy/protected data conflict, any PR dependency, or unavailable preservation facts. No ref deletion, force push, merge, backup change, public archive extension, scientific acceptance, A-line/H40 task resumption, TESTNET/LIVE/real funds.

PR protection: #3 head `c7c8d98520b21f3d36352e1ba0df408327e011fe` base `13e3a710b137efeec2e21e3002f748834ec0cc22`; #5 head `8c7693700c15f32329614a23b737d34cc7e2b0c4` base branch `v0.6-docs@2f1e4b340c56448bfa0207ee2d6fc6dded797cfd`.

Preserved hard gates: `SOURCE_NOT_ADMITTED / PIT_UNKNOWN / COST_INCOMPLETE / UTILITY_NOT_IDENTIFIED / G2_ALPHA_NO_GO / G4_TESTNET_NO_GO / LIVE_NO_GO / REAL_FUNDS_WRITE_NONE`.

This dispatch changes only 4 new Markdown documents under `repository-maintenance/v065-m5/` on its own isolated docs branch. Exact author commit, parent, blobs, diff and actual CI must be verified externally after publication; do not self-assert a future hash.
