# Windows CREON Gateway Setup

Docker Compose does not create or boot a Windows VM, and it should not be used
to install CREON Plus or handle a brokerage login session. Use this directory
for the Windows host or Windows VM that already exists.

## Supported Flow

| Step | Owner | Notes |
| --- | --- | --- |
| Create Windows host/VM | User or infrastructure tooling | Use a licensed Windows desktop/VM that can run CREON Plus interactively. |
| Install CREON Plus | User in Windows desktop session | Install from the broker-approved installer and complete any security modules. |
| Log in to CREON Plus | User in Windows desktop session | The COM API depends on this interactive login state. |
| Prepare gateway runtime | `setup-creon-gateway.ps1` | Creates 32-bit Python venv, installs gateway dependencies, writes local `.env`. |
| Run gateway | `gateway/run-creon-gateway.ps1` | Starts FastAPI on port `8765` by default. |
| Start main app | Docker Compose on app machine | Use `docker-compose.creon-gateway.yml` to point backend at the Windows gateway. |

## Windows Setup

Run from the repository root in PowerShell:

```powershell
.\infra\windows\setup-creon-gateway.ps1 `
  -GatewayToken "replace-with-a-long-random-token" `
  -CreonAccountNo "replace-with-account-number" `
  -AllowLiveTrading `
  -UnderstandLossRisk
```

If you have a local CREON installer file, the script can launch it
interactively:

```powershell
.\infra\windows\setup-creon-gateway.ps1 `
  -CreonInstallerPath "C:\Installers\CreonPlusSetup.exe" `
  -GatewayToken "replace-with-a-long-random-token" `
  -CreonAccountNo "replace-with-account-number" `
  -AllowLiveTrading `
  -UnderstandLossRisk
```

After setup, log in to CREON Plus in the Windows desktop session, then run:

```powershell
.\gateway\run-creon-gateway.ps1
```

On the app machine, configure `.env` with:

```bash
BROKER_MODE=creon_gateway
CREON_GATEWAY_URL=http://WINDOWS_HOST_IP:8765
CREON_GATEWAY_TOKEN=replace-with-a-long-random-token
ALLOW_LIVE_TRADING=true
I_UNDERSTAND_LOSS_RISK=true
AUTO_EXECUTE=false
```

Then start the main stack:

```bash
docker compose -f docker-compose.yml -f docker-compose.creon-gateway.yml up --build -d
```

Keep `AUTO_EXECUTE=false` until quote retrieval, manual order staging, approval,
and rejection paths have been tested with intentionally small limits.
