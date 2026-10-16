# Linux VPS Forward Evidence Infrastructure Migration Runbook

## 1. Executive Summary & Context

Prior to v0.3.20, forward evidence collectors ran inside a Windows Subsystem for Linux (WSL2) instance on a local Windows laptop. Forensic investigation revealed two critical reliability failure modes in this setup:
1. **Windows Modern Standby (Sleep / Suspend)**: Laptop suspension froze the WSL environment for multiple consecutive hours, preventing scheduled systemd timers from firing and breaching the maximum consecutive slot gap limit ($M_{gap} \le 4$).
2. **Local VPN/Proxy Routing**: Global proxy routing routed egress traffic through a US exit node, causing Binance REST and WebSocket endpoints to reject requests with `HTTP 451: Unavailable For Legal Reasons`.

To ensure 24/7/365 uninterrupted data integrity and institutional-grade SLA for PIT forward evidence, production collection should be hosted on a dedicated Linux Virtual Private Server (VPS).

---

## 2. Infrastructure Architecture & Host Selection

### Recommended VPS Specifications:
- **CPU**: 2 vCPUs minimum (AMD EPYC or Intel Xeon).
- **RAM**: 4 GB RAM minimum (8 GB recommended for parallel research workloads).
- **Storage**: 50 GB NVMe SSD minimum (Microstructure depth and trade events generate ~1.5 GB/day).
- **Operating System**: Ubuntu 22.04 LTS, Ubuntu 24.04 LTS, or Debian 12.
- **Network / Region**: **CRITICAL**: Egress IP must NOT be in the United States. Deploy in non-restricted regions (e.g., Frankfurt/Germany, London/UK, Tokyo/Japan, Singapore, or Helsinki/Finland). Recommended providers include Hetzner, OVHcloud, DigitalOcean, or Linode.

---

## 3. Server Provisioning & Bootstrap

Run the provider-neutral bootstrap script as `root`:

```bash
# Clone the repository to the deployment location
sudo git clone https://github.com/EXASHXE/btc-quant-agent.git /opt/btc-quant-agent
cd /opt/btc-quant-agent

# Execute the bootstrap script (creates 'quant' system user, enables linger, installs dependencies)
sudo bash deploy/linux-vps/bootstrap.sh quant
```

### Enable User Linger Manually (if not using bootstrap):
User linger is strictly required so systemd user timers and background capture services persist when interactive SSH sessions disconnect:
```bash
sudo loginctl enable-linger quant
```
Verify linger status:
```bash
loginctl show-user quant --property=Linger
# Expected output: Linger=yes
```

---

## 4. Virtual Environment & Python Dependencies

Switch to the `quant` user:
```bash
sudo -u quant -i
cd /opt/btc-quant-agent

# Create and activate Python virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Upgrade pip and install package in editable mode
pip install --upgrade pip
pip install -e .
```

---

## 5. Network & Proxy Configuration (Avoiding HTTP 451)

If the VPS is in a supported country (e.g., Germany, Japan), direct outbound internet access can be used without a proxy.
If a proxy or custom egress gateway is required, configure it in `~/.config/btc-quant-agent/network.env`:

```bash
mkdir -p ~/.config/btc-quant-agent
cat << 'EOF' > ~/.config/btc-quant-agent/network.env
PYTHONUNBUFFERED=1
BTC_QUANT_TRIGGER_SOURCE=SCHEDULED
# Only set proxy if routing through an external proxy:
# HTTP_PROXY=http://proxy-server:port
# HTTPS_PROXY=http://proxy-server:port
EOF
chmod 600 ~/.config/btc-quant-agent/network.env
```

Verify Binance reachability using `quantctl`:
```bash
quantctl forward-evidence doctor
```
Ensure `"binance_reachability": "OK"` is reported.

---

## 6. Forward Data Migration Procedure

### Rule of Data Quality Invariance:
- **NEVER** edit, delete, or retroactively backfill historical forward rows.
- Existing database files (`derivatives.sqlite3`, `opportunity_shadow.sqlite3`, and `microstructure/`) are copied as immutable audit artifacts.

### Transferring Existing Data to VPS:
On the source host (WSL), stop any active local capture before syncing:
```bash
systemctl --user stop btc-quant-microstructure-forward.service
systemctl --user stop btc-quant-forward-derivatives.timer
systemctl --user stop btc-quant-opportunity-forward.timer
```

Sync forward data directories to VPS:
```bash
rsync -avz --progress data/forward/ quant@<vps-ip>:/opt/btc-quant-agent/data/forward/
```

Verify partition integrity on the VPS:
```bash
quantctl forward-evidence doctor
```

---

## 7. Service Installation & Activation

Install all timers and services using the unified installer:
```bash
bash deploy/systemd/install-all-forward-services.sh
```

Verify active timers and services:
```bash
systemctl --user list-timers
systemctl --user status btc-quant-microstructure-forward.service --no-pager
```

---

## 8. Verification & Operational Health Check

Run the forward evidence health check and doctor:
```bash
quantctl forward-evidence health
quantctl forward-evidence doctor
```

Setup periodic automated health checks via cron:
```bash
(crontab -l 2>/dev/null; echo "*/15 * * * * /opt/btc-quant-agent/deploy/linux-vps/healthcheck.sh >> /var/log/btc-quant-health.log 2>&1") | crontab -
```

---

## 9. Rollback & Emergency Runbook

If an operational anomaly occurs:
1. **Run Doctor**: `quantctl forward-evidence doctor` to isolate whether the root cause is systemd, network/HTTP 451, or database lock contention.
2. **Safe Recovery**: Run `quantctl forward-evidence recover-services` to safely restart failed units without risking data loss or backfills.
3. **Immutability Protection**: Remember that if consecutive slots exceed 4 during an outage, the active epoch must be cleanly marked terminal and a new clean successor preregistered on a future boundary. Never attempt retroactive clock manipulation.
