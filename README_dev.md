# Trade-pilot Developer Guide

This guide is for local development and operations. The root
[README.md](./README.md) is the GitHub-facing product and architecture
overview.

## Prerequisites

| Tool | Purpose |
| --- | --- |
| Docker Desktop | Local PostgreSQL and full-stack Compose runs. |
| Python 3.11 | Backend development. |
| Node.js 20 or compatible | `user-web` and `admin-web` development. |
| OpenAI API key | Enables real planner and agent model calls. |
| Windows host or VM | Required only for CREON Plus live integration. |

## Environment

The backend reads both root `.env` and `backend/.env`. The Vite apps read the
root `.env` through their Vite config, so ports and API URLs can stay
centralized.

Minimal local `.env`:

```bash
APP_ENV=development

POSTGRES_PORT=5433
DATABASE_URL=postgresql+psycopg://trade_pilot:trade_pilot@localhost:5433/trade_pilot

BACKEND_HOST=127.0.0.1
BACKEND_PORT=8000
BACKEND_BASE_URL=http://localhost:8000

USER_WEB_HOST=127.0.0.1
USER_WEB_PORT=5174
ADMIN_WEB_HOST=127.0.0.1
ADMIN_WEB_PORT=5173
VITE_API_BASE_URL=http://localhost:8000

OPENAI_API_KEY=your-openai-key
OPENAI_MODEL=gpt-5.4-mini

ADMIN_USERNAME=admin
ADMIN_PASSWORD=change-this-password

BROKER_MODE=paper
AUTO_EXECUTE=false
ALLOW_LIVE_TRADING=false
I_UNDERSTAND_LOSS_RISK=false
```

Important variables:

| Variable | Meaning |
| --- | --- |
| `DATABASE_URL` | SQLAlchemy URL used by local backend. Docker overrides it inside the backend container. |
| `POSTGRES_PORT` | Host port exposed by Docker PostgreSQL. Use `5433` if local PostgreSQL already owns `5432`. |
| `BACKEND_PORT` | FastAPI port. |
| `USER_WEB_PORT` | User web Vite port. |
| `ADMIN_WEB_PORT` | Admin web Vite port. |
| `VITE_API_BASE_URL` | Browser-facing backend URL for both web apps. |
| `OPENAI_API_KEY` | Enables real OpenAI planner and trading agent calls. |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | Bootstrap admin credentials. Change for any shared environment. |
| `BROKER_MODE` | `paper`, `creon`, or `creon_gateway`. |
| `AUTO_EXECUTE` | If `true`, approved BUY/SELL decisions may create broker orders. Keep `false` during development. |
| `ALLOW_LIVE_TRADING` / `I_UNDERSTAND_LOSS_RISK` | Required live-trading gates. |
| `CREON_GATEWAY_URL` | Windows gateway URL when using `BROKER_MODE=creon_gateway`. |
| `CREON_GATEWAY_TOKEN` | Shared gateway token. Required when live trading is enabled. |
| `CREON_QUOTE_RETRY_COUNT` | Gateway quote retry count. Orders are not retried automatically. |
| `CREON_COM_LOCK_TIMEOUT_SECONDS` | Gateway lock wait time for serialized COM calls. |

## Full Docker Stack

Start everything in paper mode:

```bash
docker compose up --build -d
```

Check status:

```bash
docker compose ps
curl http://127.0.0.1:8000/api/health
```

Open:

| App | URL |
| --- | --- |
| User web | `http://localhost:5174` |
| Admin web | `http://localhost:5173` |
| Backend docs | `http://localhost:8000/docs` |

Stop:

```bash
docker compose down
```

Reset local database volume:

```bash
docker compose down -v
docker compose up --build -d
```

## Hybrid Local Development

Use this when you want fast backend and `user-web` iteration without rebuilding
Docker images every time. PostgreSQL still runs in Docker.

From the project root:

```bash
docker compose up -d postgres
```

Prepare backend once:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cd ..
```

Prepare `user-web` once:

```bash
cd user-web
npm install
cd ..
```

Run backend from the project root:

```bash
./scripts/dev_backend.sh
```

Run user web from another terminal, also from the project root:

```bash
./scripts/dev_user_web.sh
```

The backend script sources `.env`, activates `backend/.venv`, applies
`alembic upgrade head`, and starts Uvicorn with reload. The user web script
sources `.env` and starts Vite on `USER_WEB_HOST:USER_WEB_PORT`.

## Running Admin Web Locally

```bash
cd admin-web
npm install
npm run dev -- --host "${ADMIN_WEB_HOST:-127.0.0.1}" --port "${ADMIN_WEB_PORT:-5173}"
```

`admin-web/README.md` is intentionally ignored by git for local/private admin
runbooks.

## Backend Commands

From `backend/` with `.venv` activated:

```bash
alembic upgrade head
uvicorn app.main:app --reload
pytest
ruff check app tests
```

If an existing local database has tables but no Alembic version row, stamp the
base migration once:

```bash
alembic stamp 0001_initial
alembic upgrade head
```

## Frontend Commands

User web:

```bash
npm run typecheck --prefix user-web
npm run build --prefix user-web
```

Admin web:

```bash
npm run typecheck --prefix admin-web
npm run build --prefix admin-web
```

Legacy React Native app:

```bash
cd frontend
npm install
npm run start
```

## API Smoke Tests

Health:

```bash
curl http://127.0.0.1:8000/api/health
```

Login and authenticated assistant query:

```bash
curl -sS -c /tmp/tradepilot-cookies.txt \
  -H "Content-Type: application/json" \
  -X POST http://localhost:8000/api/auth/login \
  --data-binary '{"username":"admin","password":"change-this-password"}'
```

Use the returned `csrf_token`:

```bash
curl -sS -b /tmp/tradepilot-cookies.txt \
  -H "Content-Type: application/json" \
  -H "X-CSRF-Token: returned-csrf-token" \
  -X POST http://localhost:8000/api/assistant/query \
  --data-binary '{"query":"현재 시스템 상태와 사용 가능한 skills를 요약해줘.","quantity":1}'
```

## CREON Gateway Development

Default development should stay in `BROKER_MODE=paper`. For CREON Plus, use a
Windows host or Windows VM where CREON Plus is installed and logged in.

Prepare gateway on Windows from the repository root:

```powershell
.\infra\windows\setup-creon-gateway.ps1 `
  -GatewayToken "change-me" `
  -CreonAccountNo "replace-with-account-number" `
  -AllowLiveTrading `
  -UnderstandLossRisk

.\gateway\run-creon-gateway.ps1
```

Then run the app stack against that gateway:

```bash
CREON_GATEWAY_URL=http://WINDOWS_HOST_IP:8765
CREON_GATEWAY_TOKEN=change-me
ALLOW_LIVE_TRADING=true
I_UNDERSTAND_LOSS_RISK=true
docker compose -f docker-compose.yml -f docker-compose.creon-gateway.yml up --build -d
```

Gateway readiness checks:

```bash
curl http://WINDOWS_HOST_IP:8765/health
curl -i http://WINDOWS_HOST_IP:8765/ready
curl -H "x-trade-pilot-token: change-me" http://WINDOWS_HOST_IP:8765/quote/005930
```

`/health` is a lightweight process/runtime check. `/ready` performs a CREON
connection check and returns `503` until Windows, 32-bit Python, pywin32, live
gates, account config, gateway token, and CREON login are all available.

There is also an experimental Windows-container gateway definition:

```powershell
docker compose -f docker-compose.windows.yml up --build -d creon-gateway
```

Use it only on Windows with Docker Desktop switched to Windows containers. It
does not create a VM, install CREON Plus, or inherit the host HTS login state.
The direct Windows gateway process is the recommended live path.

Validate Compose files without printing resolved secrets:

```bash
ALLOW_LIVE_TRADING=true \
I_UNDERSTAND_LOSS_RISK=true \
CREON_GATEWAY_URL=http://127.0.0.1:8765 \
CREON_GATEWAY_TOKEN=test \
docker compose -f docker-compose.yml -f docker-compose.creon-gateway.yml config --quiet

CREON_GATEWAY_TOKEN=test docker compose -f docker-compose.windows.yml config --quiet
```

## Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `TypeError: Failed to fetch` in web UI | Backend is down, wrong `VITE_API_BASE_URL`, CORS mismatch, or port conflict. | Check `curl /api/health`, `.env`, and backend logs. |
| Docker backend cannot connect to DB | Wrong host URL inside container. | Compose backend must use `postgres:5432`; local backend uses `localhost:${POSTGRES_PORT}`. |
| Host PostgreSQL already uses `5432` | Port conflict. | Set `POSTGRES_PORT=5433` and update `DATABASE_URL` to `localhost:5433`. |
| Authenticated POST returns `403` | Missing or stale CSRF token. | Log in again and send `X-CSRF-Token`. |
| OpenAI planner does not run | `OPENAI_API_KEY` unset or model/API error. | Set key and check backend logs; fallback planner should still answer conservatively. |
| CREON direct mode fails on macOS/Linux | CREON Plus is Windows COM. | Use `creon_gateway` with a Windows gateway host. |
| Gateway `/ready` returns `503` | Windows runtime, pywin32, live gates, token, account, or CREON login is missing. | Read the `runtime.message` field and fix the missing item on the Windows host. |
| Gateway returns `creon_com_busy` | Another COM request is still running. | Retry after the current request finishes; increase `CREON_COM_LOCK_TIMEOUT_SECONDS` only after investigating slow calls. |
| Order was not submitted | `AUTO_EXECUTE=false`, risk rejected, or manual approval required. | Inspect decision `risk_status`, `risk_reasons`, and order state. |

## Safety Notes

Keep these defaults during development:

```bash
BROKER_MODE=paper
AUTO_EXECUTE=false
ALLOW_LIVE_TRADING=false
I_UNDERSTAND_LOSS_RISK=false
```

Before enabling live trading, validate quote retrieval, manual order staging,
approval, broker submission, rejection handling, and database reconciliation
with intentionally small limits.
