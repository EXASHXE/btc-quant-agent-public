# P1A/P1D code–docs relocation receipt R1

Controller dispatch: `efe0dce0773e2ac76771dda7847a4dffbe867ceb`, prompt blob `7abdbc941af9aeefcc5df5f6997df50eb8f2b268`.
Archive parent: `2c99c8f64368a02dfeca05ac1886ed2280faf3ba`.
Archive branch: `docs/v06-p1a-p1d-ci-report-archive-r1`.
The immutable commit containing this receipt is the frozen archive identity. This initial receipt precedes all code-branch changes; the final execution report records its full commit SHA and downstream CI results.

| Report | Exact original source commit | Original and archived Git blob | Full byte comparison |
| --- | --- | --- | --- |
| `V06_P1A_R2_SYNTHETIC_COST_CONTRACT_REPORT.md` | `0540e2c902ef9565cd3719e60174ac01b1c22adf` | `00945d048664445710505bc56d64ad2210be89fe` | Equal, every byte |
| `V06_P1D_CONSUMER_C_LATE_FUNDING_R2_IMPLEMENTATION_AND_EVIDENCE.md` | `81c613c3c8dc3fb22fd4d09b2d0ef4674f09c079` | `84a4448df7c85db1d0caf04cc16351fa65e248a1` | Equal, every byte |

Both destinations were absent at the pinned archive parent. Only the two original reports and this receipt are added. The copied reports preserve the original claims verbatim; archival preservation does not endorse those claims or supersede independent scientific/PIT reviews.

Stage B is limited to one respective report deletion on each separate descendant branch. All other tracked file blobs, executable source, tests, evidence JSON, CI policy and protected H40 content must remain identical to the original code commits. The archive must be committed, remotely published and identity-verified before either deletion.

Stage C requires manual `workflow_dispatch` with `profile=full` on the two exact repair heads. Automatic documentation-only CI success is insufficient. Recurring protected H40 failure remains an independent A-line hold; no golden update, test bypass, source modification, merge or trading action is authorized.

Status at archive creation: report preservation complete; code deletions and full CI are pending. No release, causal-audit or Controller merge authorization is asserted.
