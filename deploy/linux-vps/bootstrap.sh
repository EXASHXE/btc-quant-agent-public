#!/usr/bin/env bash
# ==============================================================================
# BTC Quant Agent - Linux VPS Production Bootstrap Script
# Provider-neutral setup for Ubuntu 22.04 / 24.04 LTS or Debian 12
# ==============================================================================
set -euo pipefail

APP_USER="${1:-quant}"
APP_DIR="/opt/btc-quant-agent"
REPO_URL="https://github.com/EXASHXE/btc-quant-agent.git"
PYTHON_BIN="python3"

echo "=== BTC Quant Agent VPS Bootstrap ==="
echo "Target User: ${APP_USER}"
echo "Target Dir : ${APP_DIR}"

# 1. Install base dependencies
echo "Updating apt packages..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y --no-install-recommends \
    curl \
    git \
    python3 \
    python3-venv \
    python3-pip \
    sqlite3 \
    ca-certificates \
    systemd \
    dbus \
    libpam-systemd

# 2. Create application user if not exists
if ! id "${APP_USER}" &>/dev/null; then
    echo "Creating system user ${APP_USER}..."
    useradd -m -s /bin/bash -U "${APP_USER}"
fi

# Enable linger for background user systemd services
echo "Enabling linger for ${APP_USER}..."
loginctl enable-linger "${APP_USER}"

# 3. Create app directory and set ownership
mkdir -p "${APP_DIR}"
chown "${APP_USER}:${APP_USER}" "${APP_DIR}"

echo "Bootstrap complete. Next steps:"
echo "1. Run migration as user ${APP_USER}."
echo "2. Set up virtualenv: ${PYTHON_BIN} -m venv ${APP_DIR}/.venv"
echo "3. Run installer: bash ${APP_DIR}/deploy/systemd/install-all-forward-services.sh"
