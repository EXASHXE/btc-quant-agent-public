#!/usr/bin/env bash
set -euo pipefail

repo_path="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
unit_source="${repo_path}/deploy/systemd"
unit_target="${XDG_CONFIG_HOME:-${HOME}/.config}/systemd/user"
network_env_dir="${XDG_CONFIG_HOME:-${HOME}/.config}/btc-quant-agent"
current_user="${USER:-$(id -un)}"

echo "=== BTC Quant Agent Forward Services Installer ==="
echo "Repository path : ${repo_path}"
echo "Systemd unit dir: ${unit_target}"
echo "Current user    : ${current_user}"

# 1. Ensure user linger is enabled so user systemd services survive session close
if command -v loginctl >/dev/null 2>&1; then
    linger_state="$(loginctl show-user "${current_user}" --property=Linger 2>/dev/null || true)"
    if [[ "${linger_state}" != "Linger=yes" ]]; then
        echo "Enabling user linger for ${current_user}..."
        loginctl enable-linger "${current_user}" 2>/dev/null || sudo loginctl enable-linger "${current_user}" 2>/dev/null || {
            echo "Warning: Could not enable user linger automatically. Please run: sudo loginctl enable-linger ${current_user}" >&2
        }
    else
        echo "User linger is already enabled."
    fi
fi

mkdir -p "${unit_target}"
mkdir -p "${network_env_dir}"

if [[ ! -f "${network_env_dir}/network.env" && -f "${unit_source}/network.env.example" ]]; then
    cp "${unit_source}/network.env.example" "${network_env_dir}/network.env"
    echo "Created default network.env at ${network_env_dir}/network.env"
fi

# 2. Template and install unit files replacing default path if repo_path differs
for unit in \
    btc-quant-forward-derivatives.service \
    btc-quant-forward-derivatives.timer \
    btc-quant-opportunity-forward.service \
    btc-quant-opportunity-forward.timer \
    btc-quant-opportunity-resolve.service \
    btc-quant-opportunity-resolve.timer \
    btc-quant-forward-health.service \
    btc-quant-forward-health.timer \
    btc-quant-microstructure-forward.service
do
    if [[ -f "${unit_source}/${unit}" ]]; then
        sed "s|/root/workspace/project/Quant-agent|${repo_path}|g" "${unit_source}/${unit}" > "${unit_target}/${unit}"
        chmod 0644 "${unit_target}/${unit}"
        echo "Installed ${unit}"
    fi
done

# 3. Reload systemd daemon and activate units
systemctl --user daemon-reload

echo "Activating timers..."
systemctl --user enable --now btc-quant-forward-derivatives.timer
systemctl --user enable --now btc-quant-opportunity-forward.timer
systemctl --user enable --now btc-quant-opportunity-resolve.timer
systemctl --user enable --now btc-quant-forward-health.timer

echo "Starting microstructure forward capture service..."
systemctl --user enable --now btc-quant-microstructure-forward.service

echo "All forward services installed and activated successfully."
systemctl --user list-timers --no-pager
