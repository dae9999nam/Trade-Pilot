# Trade-pilot CREON Gateway

Run this service on Windows with CREON Plus installed and logged in. Use a 32-bit Python process because CREON Plus is a 32-bit COM API.

```powershell
py -3.11-32 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:GATEWAY_TOKEN="change-me"
$env:CREON_ACCOUNT_NO="replace-with-account-number"
$env:CREON_GOODS_CODE="01"
$env:ALLOW_LIVE_TRADING="true"
$env:I_UNDERSTAND_LOSS_RISK="true"
uvicorn main:app --host 0.0.0.0 --port 8765
```

The Docker backend should call this gateway with:

```bash
BROKER_MODE=creon_gateway
CREON_GATEWAY_URL=http://WINDOWS_IP:8765
CREON_GATEWAY_TOKEN=change-me
```

## Runtime checks

| Endpoint | Auth | Purpose |
| --- | --- | --- |
| `GET /health` | no | Lightweight process and runtime status. Does not touch CREON COM. |
| `GET /ready` | no | Full readiness check. Verifies Windows/32-bit Python/pywin32/live gates/account/token and CREON connection. |
| `GET /quote/{symbol}` | token if configured | Serialized CREON quote request with bounded retry. |
| `POST /orders` | token if configured | Serialized CREON order request. Orders are not automatically retried. |

When live trading is enabled, `GATEWAY_TOKEN` is required for quote and order
requests. Gateway errors use a structured `detail` payload:

```json
{
  "detail": {
    "code": "creon_com_busy",
    "message": "CREON COM worker is busy. Try again after the current request finishes.",
    "retryable": true,
    "request_id": "..."
  }
}
```

Useful gateway tuning variables:

| Variable | Default | Notes |
| --- | --- | --- |
| `CREON_QUOTE_RETRY_COUNT` | `1` | Quote retries after retryable CREON failures. |
| `CREON_QUOTE_RETRY_BACKOFF_SECONDS` | `0.25` | Delay between quote retries. |
| `CREON_COM_LOCK_TIMEOUT_SECONDS` | `15` | Max wait for the process-wide COM lock. |

From the repository root on Windows, this helper prepares the 32-bit Python
gateway runtime and writes `gateway\.env`:

```powershell
.\infra\windows\setup-creon-gateway.ps1 `
  -GatewayToken "change-me" `
  -CreonAccountNo "replace-with-account-number" `
  -AllowLiveTrading `
  -UnderstandLossRisk
.\gateway\run-creon-gateway.ps1
```

The helper does not create a Windows VM, silently install CREON Plus, or perform
broker login. Install CREON Plus from the broker-approved installer and log in
through the Windows desktop session first.

Then start the main stack with the CREON override:

```bash
docker compose -f docker-compose.yml -f docker-compose.creon-gateway.yml up --build -d
```

## Windows container image

An experimental Windows-container image is available for gateway packaging:

```powershell
docker compose -f docker-compose.windows.yml up --build -d creon-gateway
```

On a dedicated Windows gateway machine, set `COMPOSE_FILE=docker-compose.windows.yml`
if you want plain `docker compose up --build -d` to start this service.

This requires a Windows host with Docker Desktop running Windows containers.
It is not supported from macOS Docker Desktop. The container does not
automatically inherit the host CREON Plus COM registration or logged-in HTS
session, so the direct Windows host process is the recommended live path.
