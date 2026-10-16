# V065-M3 — Owner Release Gate and Restore Verification Receipt R1

**Terminal: `M3_HOLD_PENDING_SEPARATE_OWNER_RELEASE`**. This is a **bounded M3 preflight receipt**, NOT an M3 branch-retirement completion or scientific authorization. **Actual remote deletions: 0. PR closures: 0.** This task itself expressly requires a **separate actual-user signed-in-chat release statement** for the 42 governed exact refs and an independent explicit WITHDRAW/KEEP decision for PR #3/#5. **Neither was supplied in this conversation.** Administrative permissions and recovery proofs do not waive governance.

**Frozen evidence:** [M2](https://github.com/EXASHXE/btc-quant-agent-public/blob/9cdbda447eba420b737eb741ce05e96a334b9bbf/repository-maintenance/V065_M2_FINAL_BRANCH_ARCHIVAL_AND_SAFE_RELEASE_EXECUTION_R1.md) report Git blob `a1713f2bdc8861d6d821752ba4bc7bf1c88c9804`; [M1 exact HELD_REFS](https://github.com/EXASHXE/btc-quant-agent-public/blob/9cdbda447eba420b737eb741ce05e96a334b9bbf/repository-maintenance/v065-m1-prune-r2/HELD_REFS.json), blob `27bbadacbcf9026f2e2c22ca569fb901ba160a2c`.

## Ref / governance result

- Remote GitHub REST ref refresh: **49 existing branches** = 3 permanent + 46 held; **46/46 current branch name+SHA match frozen ledger**, no unexpected changes. `v0.6.5@941f24af8f1e12c1f314e2d970e7af8f97293b21` remains default; `legacy/research-archive@0176cdde836a660420e5e4b5693591cb8108a4f6` unchanged; docs/engineering HEAD is the containing receipt commit (independently verify after publication).
- **42 government-bound refs:** 26 `HOLD_A_LINE` + 15 `HOLD_PROTECTED_CONTROL` + one `HOLD_DEFAULT_AND_A_LINE`; each exact branch/SHA/release condition is in the immutable ledger. The former default restriction is cleared, **but A-line owner release is not**. Sensitive H40/holdout ancestry **NOT** merged into public legacy. No additional control owner permissions or visibility review given.
- **4 active PR head/base refs** remain held: #3 head `c7c8d98520b21f3d36352e1ba0df408327e011fe`, base `13e3a710b137efeec2e21e3002f748834ec0cc22`; #5 head `8c7693700c15f32329614a23b737d34cc7e2b0c4`, base branch `v0.6-docs@2f1e4b340c56448bfa0207ee2d6fc6dded797cfd`. Both PRs are **OPEN/DRAFT** and **unmerged**. No withdrawal instruction, independent science acceptance or close action. No active branch dependency was disrupted.
- Effective access: authorized local `gh` logged in as EXASHXE, `repo/workflow` scopes; GitHub rulesets GET count **0**, and actual authenticated local `gh api .../branches/v0.6.5/protection` returned **404 Branch not protected**. GitHub app's separate 403 remains an integration limitation. Checks are preflight only; no per-candidate deletion-time protected-ref GET was attempted because no release-eligible candidate exists.
- No separate Gemini offline 46/46 signed restore receipt or second separately durable private backup identifier was supplied to this executing session. Do not misdescribe the independent **local** test below as a Gemini attestation or a second backup location.

## Fresh, independent M3 private backup integrity and restore proof

Read-only check at **M1 owner-approved private backup path** `/root/workspace/project/quant-v0.6/m1-remote-cleanup/backups/pre-prune-execution.bundle`: observed SHA-256 **`44e9b94242bff4bf950018d61c026639746774aeaab2472c1a65d575d537c8da`**, exactly the M1 published digest; verified with `git bundle verify` in a new temporary bare repository: **complete history / SHA-1 object format / no missing prerequisites**. Separately cloned that bundle as an isolated bare repo, fetched the 46 frozen original SHAs from the exact GitHub ledger, and independently checked **46/46 `cat-file -e <SHA>^{commit}` PASS, 0 absent**. `git fsck --connectivity-only --no-reflogs` returned **success**; only dangling synthetic PR merge commits were listed. Temporary working directories were removed. No restricted H40/holdout raw history, objects or protected outcomes were read into a model or pushed public; commit existence/structural connectivity was verified locally. One private backup location, not two verified independent durable copies: separate Gemini/durability prerequisite **NOT SATISFIED**.

## Execution and CI receipt

| Action | Actual |
| --- | --- |
| Remote branches before / after | **49 / 49**, absent external concurrent moves; one docs-only commit changes no branch count |
| Remote branch deletes, named batches, delete response receipts | **0; none attempted** because owner release missing |
| New public Git archive merges / retained sensitive graph exposure | **0** |
| PR #3/#5 close, merge, approve or branch changes | **0** |
| Local original files/workspaces `Quant-agent/data`, `history`, `Quant-agent-sanitized` or unrelated in-progress workspaces | **Untouched** |
| Main source, CI configuration, tests, security/research gates | **Unchanged** |
| Tests | **NOT_RUN** (no code/config change); M1 CI #38918484549 does NOT count as M3 CI |
| New docs/engineering workflow/checks | Inspect **after publication**; never fabricate a PASS |

**Unblocking requires an actual subsequent user message** explicitly releasing governed SHA-bound classifications, resolving control exceptions, and choosing PR #3/#5 WITHDRAW or KEEP; plus the separately durable Gemini backup receipt and fresh per-ref protection/dependency checks. No successor task, remote deletion, PR withdrawal or public archive connection is automatically authorized by this preflight.

**Preserve** `SOURCE_NOT_ADMITTED / PIT_UNKNOWN / COST_INCOMPLETE / UTILITY_NOT_IDENTIFIED / G2_ALPHA_NO_GO / G4_TESTNET_NO_GO / LIVE_NO_GO / REAL_FUNDS_WRITE_NONE`.
