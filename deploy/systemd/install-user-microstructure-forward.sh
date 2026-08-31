#!/usr/bin/env bash
set -euo pipefail
repo_path="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
unit_target="${XDG_CONFIG_HOME:-${HOME}/.config}/systemd/user"
if [[ "${repo_path}" != "/root/workspace/project/Quant-agent" ]]; then
  echo "Update committed absolute unit paths before installation." >&2
  exit 2
fi
mkdir -p "${unit_target}"
install -m 0644 "${repo_path}/deploy/systemd/btc-quant-microstructure-forward.service" "${unit_target}/"
systemctl --user daemon-reload
systemctl --user enable --now btc-quant-microstructure-forward.service
systemctl --user status --no-pager btc-quant-microstructure-forward.service
