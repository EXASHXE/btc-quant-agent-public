# BTC Quant Agent v0.3.20 — Acceptance Repair Prompt for Gemini

You are fixing the already-delivered v0.3.20 forward infrastructure recovery branch after acceptance review. Do NOT create a new research hypothesis or new Alpha family. This is a narrow correctness / operability repair round on the existing branch:

`gemini/v0.3.20-forward-infrastructure-recovery-deployment-hardening`

Current reviewed head before this repair: `4b5875b616127e27297a1de13a8b3eafc775819c`.

## Acceptance blockers to fix

### 1. CI is red on Python 3.12
GitHub Actions run `33719993032` failed only on Python 3.12:

`tests/test_v0320_reliability.py::test_network_proxy_check_detects_http_451`

Observed mismatch:

- expected: `HTTP_451_REGION_RESTRICTED`
- actual: `OK`

Python 3.11 and 3.13 passed. Ruff and mypy passed.

Find the real cause. The test currently patches `urllib.request.urlopen`; if production code imports `urlopen` directly (or otherwise binds a different symbol), patch the symbol at the actual lookup location or refactor the network probe so the behavior is deterministic and injectable across Python 3.11/3.12/3.13. Do not weaken the assertion and do not make the doctor silently return OK on HTTP 451.

Required proof:

- full CI green on Python 3.11, 3.12, 3.13;
- `ruff check .` green;
- `mypy` green;
- full pytest green;
- compileall green.

### 2. Release README currently makes a false verification claim
`deliverables/v0.3.20/README.md` says `429 passed ... zero failures`, but the pushed PR CI has `1 failed, 428 passed` on Python 3.12.

After fixing CI, update the verification section to cite the actual final GitHub Actions run ID and per-version result. Never claim a result that is only local.

### 3. Successor activation must be verified from post-start evidence
The successors were preregistered for `2026-09-03T06:30:00Z`, which is valid because registration/commit occurred before start. However, the committed doctor and health reports were captured pre-start and still showed:

- HTTP 451 through the US proxy node;
- `Linger=no`;
- derivatives latest slot FAILED;
- opportunity latest slot MISSED_DECISION_SLOT;
- stale microstructure heartbeat;
- overall status DEGRADED.

Do NOT treat `ACTIVE_ACCUMULATING` in config as evidence that the successors are actually healthy.

Run post-start operational verification on the real local WSL machine after the network route is fixed. Produce immutable snapshots showing, at minimum:

- `DERIVATIVES_PIT_EPOCH_V0320_001`: expected slots since 06:30Z, recorded, fully available, partial, failed, missing, max bad/missing streak, required-field coverage;
- `OPPORTUNITY_FORWARD_V0320_20260903T063000Z` / H37: expected scans, successful scans, misses, success ratio, max miss streak;
- microstructure: heartbeat age, aggTrade/depth activity, sequence continuity, partition integrity, daemon PID/service state;
- systemd user state and whether linger is actually enabled;
- network doctor result and explicit Binance reachability result.

If HTTP 451 is still present, do not fabricate a healthy result and do not move the successor start. Mark the successor evidence as compromised/at-risk according to frozen rules. Do not backfill missed slots.

### 4. WSL linger remediation must be actually applied or clearly remain operator-required
The deliverable says installers automate `loginctl enable-linger`, but the same committed health snapshot says `user_linger_enabled=false`.

Verify the actual installed state. If permissions/platform prevent automatic enablement, fail closed and report a concrete operator step; do not claim remediation complete.

### 5. PR hygiene
PR #20 targets stale `main`, so GitHub shows ~156 commits / 373 changed files even though the actual v0.3.20 delta from v0.3.19 formal head `eaa75330854d54e9967f3c0c0446bd6d4b34a76e` is only the prompt plus v0.3.20 implementation.

Do not merge to main. Do not rewrite historical commits. In the PR body, explicitly add a `Review lineage` section stating:

- v0.3.19 base SHA: `eaa75330854d54e9967f3c0c0446bd6d4b34a76e`;
- v0.3.20 implementation delta should be reviewed against that SHA;
- `main` is intentionally stale and PR file count is not the v0.3.20 delta.

If a cleaner stacked PR/base branch is appropriate and can be created without rewriting evidence history, do so; otherwise leave PR open and document the lineage clearly.

## Preserve good v0.3.20 work
Do not undo the following unless tests prove a defect:

- archival of terminal v0.3.16 derivatives and H36 chains;
- no backfill / no history rewrite;
- future-fixed v0.3.20 successor preregistration;
- clock-alignment crash fix;
- microstructure heartbeat supervision;
- partition/status caching optimization;
- forward doctor diagnostics;
- VPS deployment profile;
- research-download concurrency policy;
- execution disabled / Final Holdout sealed / Direction NONE.

## Deliverables
Update `deliverables/v0.3.20/` with:

1. `ACCEPTANCE_REPAIR_REPORT.md`
2. `POST_START_SUCCESSOR_HEALTH.json`
3. corrected `FORWARD_DOCTOR_REPORT.json` or a timestamped post-start successor report without overwriting evidence provenance ambiguously;
4. corrected README verification section;
5. CI provenance: final head SHA, GitHub Actions run ID, 3.11/3.12/3.13 results;
6. exact statement whether successors are `HEALTHY_ACCUMULATING`, `AT_RISK`, or `TERMINAL` based on observed post-start data, not config labels.

Commit and push all fixes to the same branch. Keep PR #20 open. Do not merge automatically.
