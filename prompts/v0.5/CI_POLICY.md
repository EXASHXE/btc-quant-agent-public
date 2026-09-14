# v0.5 CI Policy — Cost-aware validation for private repository

This policy replaces the old requirement that every implementation push run the entire suite twice on Python 3.11, 3.12 and 3.13.

## Routine automatic gate

Every push / pull request on the implementation branch should pass the automatic Python 3.13 gate:

1. install `.[dev,research]`
2. `ruff check .`
3. `mypy`
4. one full `pytest -q` run
5. `python -m compileall -q src skill-template/scripts`

Do not run a second duplicate pytest pass for coverage on routine pushes.

The implementation workflow uses concurrency cancellation so a newer push cancels an obsolete in-progress run on the same branch/ref.

## Manual full compatibility gate

Use GitHub Actions `workflow_dispatch` on `v0.5-refactor` when a stage requires a formal compatibility receipt. The manual gate runs:

- Python 3.13: Ruff, mypy, full pytest with coverage, compileall
- Python 3.11: full pytest, compileall
- Python 3.12: full pytest, compileall

Coverage is informational unless a future explicit threshold is introduced; there is currently no `fail_under` coverage threshold in `pyproject.toml`.

## When the manual full gate is REQUIRED

Run and record an exact-HEAD manual full compatibility gate before accepting any of the following:

- R03 contract / data-model simplification when formal identities or persisted schemas change
- R04 research-kernel convergence
- any change touching formal replay authority, qualification authority, benchmark reconstruction, publication/finalization semantics, H39 protected authority or Final Holdout boundary
- Astra simplified-kernel/final stage gate
- release/freeze/tag candidate
- any change whose reviewer explicitly escalates compatibility risk

## When the manual full gate is NOT required

The Python 3.13 automatic gate is sufficient for ordinary bounded changes such as:

- dead-code / historical-surface deletion with protected-byte checks
- documentation-only or metadata-only changes
- CLI/help text cleanup that does not alter formal authority
- import/orchestration cleanup covered by existing semantic differential tests
- narrow non-semantic test maintenance

A reviewer may still request the manual matrix when the actual diff is riskier than its task label.

## Dedicated docs branch

`v0.5-refactor-docs` stores prompts and review/audit reports. Commits changing only:

- `prompts/**`
- `reviews/**`
- `REFACTOR_DOCS_BRANCH.md`

do not automatically run repository CI. Production/source changes do not belong on this branch; if such a path changes, the docs-branch safety workflow remains eligible to run.

## Acceptance wording

Routine implementation acceptance should distinguish the two levels:

```text
FAST_CI_GREEN_PY313
```

versus a formal stage compatibility receipt:

```text
FULL_COMPAT_CI_GREEN_PY311_PY312_PY313
```

Do not claim the latter unless the exact reviewed implementation HEAD has a successful manually triggered compatibility run.
