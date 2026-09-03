#!/usr/bin/env bash
# ==============================================================================
# BTC Quant Agent - Linux VPS Automated Health Check
# Can be run via cron or systemd watchdog timer
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PYTHON="${REPO_DIR}/.venv/bin/python"
QUANTCTL="${REPO_DIR}/.venv/bin/quantctl"

if [[ ! -x "${QUANTCTL}" ]]; then
    echo "ERROR: quantctl not found at ${QUANTCTL}" >&2
    exit 1
fi

echo "=== Forward Evidence Health Check ==="
HEALTH_OUTPUT="$("${QUANTCTL}" forward-evidence health)"
echo "${HEALTH_OUTPUT}"

STATE="$(echo "${HEALTH_OUTPUT}" | "${PYTHON}" -c "import sys, json; print(json.load(sys.stdin).get('state', 'UNKNOWN'))")"

if [[ "${STATE}" != "HEALTHY" ]]; then
    echo "WARNING: Forward evidence state is ${STATE}." >&2
    echo "Running doctor diagnostics..." >&2
    "${QUANTCTL}" forward-evidence doctor >&2
    exit 2
fi

echo "Forward evidence services are healthy."
exit 0
