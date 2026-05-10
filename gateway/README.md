# Stock Pilot CREON Gateway

Run this service on Windows with CREON Plus installed and logged in. Use a 32-bit Python process because CREON Plus is a 32-bit COM API.

```powershell
py -3.11-32 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:GATEWAY_TOKEN="change-me"
$env:CREON_ACCOUNT_NO="123456789"
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

