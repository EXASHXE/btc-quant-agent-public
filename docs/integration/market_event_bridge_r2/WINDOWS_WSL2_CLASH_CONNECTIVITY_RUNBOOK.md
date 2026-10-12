# Windows / WSL2 Clash Connectivity & Network Routing Runbook

## 1. Executive Summary

This document specifies the operational runbook and architecture for reliable, desensitized, and fail-closed egress connectivity from a Linux WSL2 development environment through a Windows-hosted Clash/Mihomo proxy core to official Binance USDⓈ-M Futures market data endpoints (`fstream.binance.com` and `fapi.binance.com`).

All network operations adhere strictly to the **zero-account, zero-order, read-only public egress contract** required by Gemini Goal R2 (`V06_GEMINI_GOAL_ABC_R2_CLASH_ROUTED_PUBLIC_SOURCE_PIT_BRIDGE`).

---

## 2. Environment & Network Topology

```
+-------------------------------------------------------------------------------+
| Windows 11 Host                                                               |
|                                                                               |
|   +-----------------------------------------------------------------------+   |
|   | Clash / Mihomo Core (e.g., Clash Verge Rev, Mihomo Party)             |   |
|   | Local HTTP / SOCKS5 Listener: 127.0.0.1:7897 / 0.0.0.0:7897           |   |
|   +-----------------------------------------------------------------------+   |
|          ^                                                                    |
|          | (Loopback or Hyper-V Internal Switch)                              |
|          v                                                                    |
|   +-----------------------------------------------------------------------+   |
|   | WSL2 Linux Subsystem (Ubuntu 24.04 / Kernel 6.6.x-microsoft-WSL2)     |   |
|   |   - Mirrored Mode: `127.0.0.1:7897` directly reachable                |   |
|   |   - NAT Mode: Resolved via `/etc/resolv.conf` nameserver or gateway   |   |
|   |                                                                       |   |
|   |   +---------------------------------------------------------------+   |   |
|   |   | Python 3.12 Integration Runtime (proxy_route.py, connector.py)|   |   |
|   |   | Unified REST & WS proxy transport (python-socks + urllib)      |   |   |
|   |   +---------------------------------------------------------------+   |   |
|   +-----------------------------------------------------------------------+   |
+-------------------------------------------------------------------------------+
                               |
                               | (Clash Egress via Outbound Tunnel)
                               v
                     +-------------------+
                     | Binance USDⓈ-M    |
                     | 2026 Routed Feed  |
                     +-------------------+
```

### 2.1 WSL2 Networking Modes
1. **Mirrored Mode (`networkingMode=mirrored`)**: The Linux subsystem shares the host's localhost interfaces. Connecting to `127.0.0.1:7897` connects directly to the Windows proxy daemon.
2. **NAT Mode (Default Legacy)**: The Linux subsystem resides in a virtual switch network. The Windows host is reached via the default gateway extracted from `/etc/resolv.conf` or `ip route show default`.

The bridge engine dynamically detects whether WSL2 is active using `detect_wsl2_networking()`:
- Inspects `/proc/version` for `microsoft` or `wsl`.
- Inspects `/etc/resolv.conf` and routing table for gateway IPs.
- Selects `127.0.0.1` as primary candidate, falling back to the discovered gateway IP.

---

## 3. Explicit Egress Route Specification

Ambient environment proxy variables (`HTTP_PROXY`, `ALL_PROXY`) can cause split-brain routing where REST uses the proxy but WebSockets connect direct, or vice versa. To prevent this, the R2 bridge mandates **explicit, unified egress configuration**:

```python
from scripts.market_data.forward_public_feed_r1.proxy_route import ProxyRouteConfig

config = ProxyRouteConfig(
    mode="public-clash-explicit",  # disabled | public-direct | public-clash-explicit
    kind="http",                  # http (HTTP CONNECT) | socks5h (SOCKS5 with remote DNS)
    host="127.0.0.1",
    port=7897,
    route_epoch="route-epoch-1",
    timeout_seconds=10.0,
)
```

### 3.1 Supported Protocols
- **`http`**: Uses standard HTTP `CONNECT` tunneling. Fully compatible with both Python's standard library `urllib` and `python-socks` / `websockets`.
- **`socks5h`**: Uses SOCKS5 proxy protocol with **remote DNS resolution**, ensuring that DNS lookup occurs on the proxy egress node, mitigating local DNS poisoning or geo-blocking.

---

## 4. 4-Layer Diagnostic Protocol

Before initiating public streams, the system executes an automated, desensitized 4-layer diagnostic state machine (`run_desensitized_network_diagnostic`):

```
+-----------------------------------------------------------------------------------+
| Layer 1: Local TCP Socket Probe                                                   |
| Verify TCP socket opens to `host:port` within timeout (e.g., 127.0.0.1:7897).     |
| Fail: PROXY_PORT_CLOSED                                                           |
+-----------------------------------------------------------------------------------+
                                         | Success
                                         v
+-----------------------------------------------------------------------------------+
| Layer 2: Proxy Negotiation                                                        |
| Verify HTTP CONNECT or SOCKS5 greeting handshake succeeds without auth rejection. |
| Fail: PROXY_AUTH_REQUIRED / PROXY_CONNECT_FAILED                                  |
+-----------------------------------------------------------------------------------+
                                         | Success
                                         v
+-----------------------------------------------------------------------------------+
| Layer 3: REST TLS End-to-End Verification                                         |
| Execute shallow GET request to official 2026 REST endpoint:                       |
| `https://fapi.binance.com/fapi/v1/depth?symbol=BTCUSDT&limit=5`                  |
| Verify TLS certificate authority and valid HTTP 200 response.                     |
| Fail: TLS_CERT_INVALID / REST_TLS_EOF / SOURCE_UNAVAILABLE                        |
+-----------------------------------------------------------------------------------+
                                         | Success
                                         v
+-----------------------------------------------------------------------------------+
| Layer 4: WebSocket Connect Verification                                           |
| Verify WebSocket handshake upgrade to routed public WebSocket URL.                |
| Fail: WS_UPGRADE_FAILED                                                           |
+-----------------------------------------------------------------------------------+
```

---

## 5. Security & Desensitization Rules

1. **Fail-Closed by Default**: Without `--network public-direct` or `--network public-clash-explicit`, the entire connector and bridge remain strictly offline (`network_mode="disabled"`). No outbound sockets are created.
2. **Desensitization of Credentials**: If proxy URLs contain basic authentication (`http://user:pass@host:port`), `sanitize_env_proxy_map()` and `ProxyRouteConfig.to_sanitized_dict()` mask passwords and sensitive tokens (`***:***`).
3. **No Ambient Leaks**: Opener directories explicitly unregister default system handlers to prevent accidental bypass.
4. **No Private Endpoints**: Routing to `/private/stream`, `dapi`, `spot`, or `ws-fapi` immediately triggers `BINANCE_ROUTING_INVALID`.

---

## 6. CLI Operational Commands

### 6.1 Inspect Proxy & Environment Diagnostics
```bash
python -m scripts.integration.market_event_bridge_r2 proxy-diagnostic \
    --network public-clash-explicit \
    --proxy-kind http \
    --proxy-host 127.0.0.1 \
    --proxy-port 7897 \
    --report-out evidence/v0.6/b_line/market_event_bridge_r2/NETWORK_ROUTE_DIAGNOSTIC.json
```

### 6.2 Offline Hermetic Bridge Verification
```bash
python -m scripts.integration.market_event_bridge_r2 bridge-check \
    --evidence-dir evidence/v0.6/b_line/market_event_bridge_r2
```

### 6.3 Generate High-Frequency Simulation Fixtures
```bash
python -m scripts.integration.market_event_bridge_r2 fixture \
    --scenario happy_path_10m \
    --output-file /tmp/fixture_10m.jsonl
```

### 6.4 Bounded Public Source Smoke Test (Optional Live Smoke)
```bash
python -m scripts.integration.market_event_bridge_r2 public-source-smoke \
    --network public-clash-explicit \
    --proxy-kind http \
    --proxy-host 127.0.0.1 \
    --proxy-port 7897 \
    --duration-seconds 10
```

---

## 7. Troubleshooting Guide

| Symptom / Error Code | Root Cause | Remediation Step |
|---|---|---|
| `PROXY_PORT_CLOSED` | Clash core is not running, or listening on wrong port (e.g. 7890 instead of 7897). | Verify Clash is running. Check "Mixed Port" in Clash settings. Pass `--proxy-port 7897`. |
| `PROXY_CONNECT_FAILED` | In NAT mode, Clash is bound only to `127.0.0.1` and rejecting external WSL2 packets. | Enable "Allow LAN" in Clash settings, or switch WSL2 to `networkingMode=mirrored` in `.wslconfig`. |
| `REST_TLS_EOF` / `TLS_CERT_INVALID` | TLS interception / MITM is active on proxy without matching trusted CA cert. | Disable MITM in proxy core, or ensure CA cert is installed in system trust store. |
| `BINANCE_ROUTING_INVALID` | Request URL attempted to access deprecated `/stream` or unauthorized `dapi`/`spot`. | Verify stream URLs use `/public/stream` (for diff depth) or `/market/stream` (for market data). |
| `CLOCK_UNCERTAIN` | Out-of-order frames received across route switch without epoch increment. | Advance connection epoch (`switch_route_node()`) to re-sync sequence numbers. |
