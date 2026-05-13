# Trade-pilot

Trade-pilot is a multi-agent AI trading app scaffold for Korean equities. It uses:

- Python FastAPI backend
- PostgreSQL
- LangChain and OpenAI models for agent decisions
- CREON Plus / CYBOS Plus adapter for Daishin Securities
- React Native / Expo frontend

The app defaults to paper trading. Live trading is blocked unless both `ALLOW_LIVE_TRADING=true` and `I_UNDERSTAND_LOSS_RISK=true` are set, and the broker mode is `creon`.

## Important CREON Plus constraints

CREON Plus is a Windows COM API. The official FAQ states the API caller must be 32-bit, even on a 64-bit OS. Run the live broker gateway on Windows with 32-bit Python and CREON Plus installed/logged in. The backend can be developed on macOS in paper mode.

Docker cannot create a Windows COM environment on macOS or Linux. Use Docker for PostgreSQL and the application backend, then run the CREON gateway as a native Windows process or inside a full Windows VM with an interactive desktop session.

## Quick start

```bash
cp .env.example .env
docker compose up -d postgres
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload
```

Open another terminal:

```bash
cd frontend
npm install
npm run start
```

For the web admin dashboard:

```bash
cd admin-web
npm install
npm run dev
```

Open `http://localhost:5173` and log in with `ADMIN_USERNAME` and `ADMIN_PASSWORD` from `.env`.

## API flow

1. The frontend sends a decision request for a symbol.
2. `MarketDataService` fetches a quote from the active broker.
3. Specialist agents produce verdicts:
   - market analyst
   - risk analyst
   - portfolio analyst
   - execution analyst
4. The supervisor agent emits one structured trade decision.
5. `RiskManager` applies deterministic limits before any order is created.
6. If `AUTO_EXECUTE=true`, the order is sent to the active broker. Otherwise it waits for manual approval.

## User-facing apps

- React Native mobile app: decision request, AI agent votes, orders, approval, and positions.
- Web admin dashboard: the same trading controls plus login, account summary, recent transactions, and recent AI decisions.

## Environment needed for live trading

- Daishin Securities account
- CREON Plus agreement completed
- CREON Plus installed and logged in
- Windows host
- 32-bit Python environment
- `pywin32` installed
- Account number and goods code configured

## Windows CREON gateway

On the Windows machine or Windows VM:

```powershell
cd gateway
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

In the Docker backend `.env`:

```bash
BROKER_MODE=creon_gateway
CREON_GATEWAY_URL=http://WINDOWS_VM_IP:8765
CREON_GATEWAY_TOKEN=change-me
ALLOW_LIVE_TRADING=true
I_UNDERSTAND_LOSS_RISK=true
```

## Safety defaults

- `BROKER_MODE=paper`
- `AUTO_EXECUTE=false`
- `ALLOW_LIVE_TRADING=false`
- `I_UNDERSTAND_LOSS_RISK=false`
- confidence gate before creating executable orders
- max order, position, and daily loss caps

This is engineering scaffolding, not financial advice. Test with paper trading and small mock limits before connecting real accounts.
