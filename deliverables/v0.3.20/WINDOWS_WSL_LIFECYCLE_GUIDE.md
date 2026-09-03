# Windows WSL Lifecycle & Forward Operations Guide (v0.3.20)

## 1. Understanding the Windows / WSL Standby Hazard

Windows laptops implement **Modern Standby (Connected Standby / S0 Low Power Idle)**. When the laptop screen turns off or the lid is closed:
- CPU cores enter deeply throttled C-states or suspend completely.
- Network connections are severed or deprioritized.
- **The entire WSL virtual machine is frozen in place**.

During modern standby, systemd timers cannot fire. When the host wakes up hours later, timers fire immediately for the current timestamp, but all intervening decision slots are missed. A freeze exceeding 60 minutes results in 4+ consecutive missed 15-minute slots, **permanently failing the forward campaign data quality gate**.

---

## 2. Windows-Side Sleep Prevention

To maintain continuous 24/7 collection while operating on Windows:

### Method 1: Automated Execution State Assertion (Recommended)
Run the dedicated PowerShell sleep blocker from an administrator terminal:
```powershell
powershell -ExecutionPolicy Bypass -File scripts\windows\prevent_sleep.ps1
```
This invokes `SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_AWAYMODE_REQUIRED)`, preventing Windows from entering standby while allowing screens to sleep.

### Method 2: Windows Power & Battery Settings
In Windows Settings (`Settings > System > Power & battery`):
- Set "When plugged in, put my device to sleep after" to **Never**.
- In Control Panel `Power Options > Change plan settings > Advanced power settings > Sleep`:
  - Allow Away Mode: **Enable**.
  - Sleep after: **0 (Never)**.

---

## 3. WSL Systemd & Linger Configuration

WSL user-level systemd services terminate when the last terminal window closes unless user linger is explicitly enabled.

### Verification & Enabling:
Inside WSL:
```bash
loginctl show-user $USER --property=Linger
# If Linger=no:
sudo loginctl enable-linger $USER
```
With linger enabled, systemd user managers remain active in the background even if all interactive WSL bash sessions are closed.

---

## 4. Local Proxy Management (Avoiding HTTP 451)

Binance enforces geo-fencing against US IP addresses. If you run a local proxy client (e.g., Clash Verge Rev, v2ray, Clash for Windows):
1. **Rule Mode (Recommended)**: Set proxy to **Rule** mode rather than **Global** mode. Configure Binance domains (`*.binance.com`, `*.binance.vision`) to route via non-US proxy nodes (e.g., Japan, Hong Kong, Singapore, or Germany).
2. **Global Mode Caution**: If Global mode is active, NEVER select a node located in the United States.
3. **Verification**:
   Run:
   ```bash
   quantctl forward-evidence doctor
   ```
   Confirm that `"binance_reachability": "OK"` is displayed. If `"HTTP_451_REGION_RESTRICTED"` appears, immediately switch your proxy node.

---

## 5. Monitoring WSL Health from Windows

Run the Windows monitoring helper from PowerShell:
```powershell
powershell -ExecutionPolicy Bypass -File scripts\windows\check_wsl_health.ps1
```
This tests WSL instance status, port 7897 connectivity, and invokes `quantctl forward-evidence doctor` to display end-to-end forward operations health.
