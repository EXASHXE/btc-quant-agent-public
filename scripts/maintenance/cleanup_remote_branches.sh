#!/usr/bin/env bash
set -euo pipefail

# Safe cleanup for historical stacked research branches.
# Default: dry-run. Use --apply only after main has been fast-forwarded to the accepted lineage.

MODE="dry-run"
if [[ "${1:-}" == "--apply" ]]; then
  MODE="apply"
fi

KEEP=(
  "main"
  "gemini/v0.3.20-forward-infrastructure-recovery-deployment-hardening"
)

CANDIDATES=(
  "codex/v0.2.2-research-hardening"
  "codex/v0.3.0-quant-research"
  "codex/v0.3.1-signal-funnel-diagnostic"
  "codex/v0.3.2-minimal-mechanism-experiments"
  "codex/v0.3.3-geometry-excursion-audit"
  "codex/v0.3.4-causal-entry-directionality"
  "codex/v0.3.5-breakout-edge-qualification"
  "codex/v0.3.6-directional-architecture-reset"
  "codex/v0.3.7-funding-crowding-qualification"
  "codex/v0.3.8-funding-stability-diagnostic"
  "codex/v0.3.9-cross-asset-breadth-qualification"
  "codex/v0.3.10-range-mean-reversion-qualification"
  "codex/v0.3.11-runtime-alignment-forward-data"
  "codex/v0.3.12-spot-perp-taker-flow-qualification"
  "codex/v0.3.13-opportunity-forward-shadow-reliability"
  "codex/v0.3.14-forward-evidence-gate-repair-operations-hardening"
  "codex/v0.3.15-microstructure-forward-data-foundation"
  "codex/v0.3.16-forward-evidence-recovery-microstructure-reliability"
  "codex/v0.3.17-opportunity-successor-forward-stabilization"
  "codex/v0.3.18-historical-proxy-symbolic-alpha-factory"
  "codex/v0.3.19-official-derivatives-feature-expansion-gate-hardening"
  "tmp-noop-do-not-use"
  "tmp-v0317-prompt-base"
  "tmp-v0318-placeholder"
)

git fetch origin --prune

main_sha="$(git rev-parse origin/main)"
echo "origin/main=$main_sha"
echo "mode=$MODE"

is_kept() {
  local branch="$1"
  for keep in "${KEEP[@]}"; do
    [[ "$branch" == "$keep" ]] && return 0
  done
  return 1
}

for branch in "${CANDIDATES[@]}"; do
  if is_kept "$branch"; then
    echo "KEEP $branch"
    continue
  fi

  if ! git show-ref --verify --quiet "refs/remotes/origin/$branch"; then
    echo "SKIP missing $branch"
    continue
  fi

  branch_sha="$(git rev-parse "origin/$branch")"
  if git merge-base --is-ancestor "$branch_sha" "$main_sha"; then
    echo "SAFE ancestor $branch @ $branch_sha"
    if [[ "$MODE" == "apply" ]]; then
      git push origin --delete "$branch"
    fi
  else
    echo "BLOCKED non-ancestor $branch @ $branch_sha" >&2
    exit 2
  fi
done

echo "Done. Historical protocols/prompts/deliverables remain in main; only redundant branch refs are targeted."
