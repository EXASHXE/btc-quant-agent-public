#!/usr/bin/env bash
set -euo pipefail

unit_source="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
unit_target="${XDG_CONFIG_HOME:-${HOME}/.config}/systemd/user"

install -d "${unit_target}"
install -m 0644 "${unit_source}/btc-quant-forward-health.service" "${unit_target}/"
install -m 0644 "${unit_source}/btc-quant-forward-health.timer" "${unit_target}/"
systemctl --user daemon-reload
systemctl --user enable --now btc-quant-forward-health.timer
systemctl --user status --no-pager btc-quant-forward-health.timer
