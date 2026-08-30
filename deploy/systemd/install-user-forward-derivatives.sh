#!/usr/bin/env bash
set -euo pipefail

repo_path="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
unit_source="${repo_path}/deploy/systemd"
unit_target="${XDG_CONFIG_HOME:-${HOME}/.config}/systemd/user"
python_path="${repo_path}/.venv/bin/python"
store_path="${repo_path}/data/forward/BTCUSDT/derivatives.sqlite3"

echo "Repository: ${repo_path}"
echo "Python: ${python_path}"
echo "Forward store: ${store_path}"
echo "Unit directory: ${unit_target}"

if [[ "${repo_path}" != "/root/workspace/project/Quant-agent" ]]; then
  echo "The committed unit files target /root/workspace/project/Quant-agent." >&2
  echo "Update WorkingDirectory, ExecStart, and Documentation before installation." >&2
  exit 2
fi

mkdir -p "${unit_target}"
install -m 0644 "${unit_source}/btc-quant-forward-derivatives.service" "${unit_target}/"
install -m 0644 "${unit_source}/btc-quant-forward-derivatives.timer" "${unit_target}/"
systemctl --user daemon-reload
systemctl --user enable --now btc-quant-forward-derivatives.timer
systemctl --user status --no-pager btc-quant-forward-derivatives.timer
