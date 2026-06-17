# Trade-pilot

Trade-pilot is a Korean-equity trading assistant scaffold. It combines a
FastAPI backend, PostgreSQL, OpenAI/LangChain agent workflows, deterministic
risk gates, paper trading, optional CREON Plus integration, an analyst-style
React web workspace, an admin dashboard, and a retained React Native app.

The default mode is paper trading. Live trading is blocked unless explicit
environment gates are enabled and the active broker is `creon` or
`creon_gateway`.

## System Overview

| Area                | Component                                     | Responsibility                                                                                                                                                                                                                                     |
| ------------------- | --------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| User workspace      | `user-web`                                    | Query-centered analyst UI at `http://localhost:5174`. Sends natural-language requests to `/api/assistant/query` and renders text, tables, metric grids, line charts, bar charts, pie charts, decision cards, and browser-style research artifacts. |
| Admin console       | `admin-web`                                   | Admin-role dashboard at `http://localhost:5173` for summary, positions, transactions, recent decisions, manual orders, and order approval.                                                                                                         |
| Legacy mobile       | `frontend`                                    | React Native / Expo app retained while the user-facing experience migrates to web.                                                                                                                                                                 |
| API backend         | `backend/app/api/routes.py`                   | FastAPI routes under `/api` for assistant queries, AI decisions, orders, positions, cookie-session auth, and dashboard data.                                                                                                                       |
| Assistant planner   | `backend/app/services/assistant_workspace.py` | Interprets a user request as a complete objective, selects all needed SKILLS/capabilities, runs multiple capabilities when needed, and explains missing skills instead of forcing one intent.                                                      |
| Skill catalog       | `backend/app/skills/*.md`                     | Markdown skill cards injected into prompts. They describe endpoints, variables, required parameters, safety rules, broker behavior, and missing capability boundaries.                                                                             |
| Agent orchestration | `backend/app/services/agent_orchestrator.py`  | Runs specialist agents and a supervisor for trading decisions. Uses SKILLS as prompt ground truth and avoids inventing APIs or fields.                                                                                                             |
| Trading engine      | `backend/app/services/trading_engine.py`      | Persists agent runs and trade decisions, runs risk checks, creates orders, and handles order approval.                                                                                                                                             |
| Risk gate           | `backend/app/services/risk.py`                | Deterministic boundary for confidence, quantity, notional, position limit, human approval, and live-trading gates.                                                                                                                                 |
| Market data         | `backend/app/market/data.py`                  | Builds `MarketSnapshot` from request-provided `last_price` or active broker quote.                                                                                                                                                                 |
| Broker adapters     | `backend/app/broker/*`                        | Paper broker, direct CREON COM broker, and HTTP CREON gateway broker.                                                                                                                                                                              |
| Database            | PostgreSQL                                    | Stores users, server-side sessions, agent runs, trade decisions, orders, and positions.                                                                                                                                                            |
| CREON gateway       | `gateway`                                     | Windows-native FastAPI service for CREON Plus COM quote and order calls.                                                                                                                                                                           |

## System Architecture

```mermaid
flowchart LR
  User["User"] --> UserWeb["user-web<br/>Analyst Workspace"]
  Admin["Admin"] --> AdminWeb["admin-web<br/>Control Dashboard"]
  Mobile["Legacy mobile user"] --> MobileApp["frontend<br/>React Native / Expo"]

  UserWeb --> API["FastAPI Backend<br/>/api"]
  AdminWeb --> API
  MobileApp --> API

  API --> Assistant["AssistantWorkspace<br/>query planner"]
  API --> Engine["TradingEngine"]
  API --> Auth["Auth<br/>HttpOnly session cookie + CSRF"]
  API --> DB["PostgreSQL"]

  Assistant --> Skills["SKILLS catalog<br/>Markdown cards"]
  Assistant --> Engine
  Assistant --> DB
  Assistant --> Artifacts["Assistant artifacts<br/>tables, charts, web tabs"]

  Engine --> Orchestrator["AgentOrchestrator<br/>specialists + supervisor"]
  Orchestrator --> Skills
  Orchestrator --> OpenAI["OpenAI API"]
  Engine --> Risk["RiskManager<br/>deterministic gates"]
  Engine --> DB
  Engine --> BrokerFactory["Broker factory"]

  BrokerFactory --> Paper["PaperBroker"]
  BrokerFactory --> CreonDirect["CreonBroker<br/>Windows COM"]
  BrokerFactory --> CreonGatewayBroker["CreonGatewayBroker<br/>HTTP client"]
  CreonGatewayBroker --> Gateway["Windows CREON Gateway"]
  Gateway --> Creon["CREON Plus / CYBOS Plus<br/>32-bit Windows COM"]
```

## Assistant Query Flow

The user-facing app no longer treats a request as one fixed intent. It asks the
assistant planner to solve the full request, select all available skills needed
for that solution, execute every connected workspace capability that applies,
and explicitly report any missing skill.

```mermaid
flowchart TD
  Query["User query"] --> Planner["AssistantWorkspace planner"]
  Planner --> Objective["Define complete objective"]
  Objective --> SkillCheck["Inspect SKILLS catalog"]
  SkillCheck --> Existing["Select existing skill cards"]
  SkillCheck --> Missing["List missing skills/integrations"]
  Existing --> Capabilities["Choose all needed workspace capabilities"]

  Capabilities --> Portfolio["portfolio_review"]
  Capabilities --> Orders["order_review"]
  Capabilities --> History["decision_history"]
  Capabilities --> Status["system_status"]
  Capabilities --> WebResearch["web_research<br/>tab scaffold"]
  Capabilities --> Decision["trade_decision"]

  Portfolio --> DBArtifacts["Database artifacts<br/>tables + charts"]
  Orders --> DBArtifacts
  History --> DBArtifacts
  Status --> DBArtifacts
  WebResearch --> ResearchArtifact["Browser-style research artifact"]
  Decision --> DecisionArtifacts["Decision card + price line + vote bars + risk table"]

  Missing --> Coverage["Skill coverage plan table"]
  DBArtifacts --> Response["AssistantQueryResponse"]
  ResearchArtifact --> Response
  DecisionArtifacts --> Response
  Coverage --> Response
```

## Trading Decision Flow

```mermaid
sequenceDiagram
  participant UI as User Web or Admin Web
  participant API as FastAPI
  participant Market as MarketDataService
  participant Engine as TradingEngine
  participant Agents as AgentOrchestrator
  participant OpenAI as OpenAI
  participant Risk as RiskManager
  participant DB as PostgreSQL
  participant Broker as Broker Adapter

  UI->>API: POST /api/assistant/query or /api/decisions/run
  API->>Market: Build MarketSnapshot
  Market->>Broker: get_quote(symbol), unless last_price was provided
  API->>Engine: run_decision(request, snapshot)
  Engine->>Agents: run specialists and supervisor
  Agents->>OpenAI: Structured model calls with SKILLS catalog
  OpenAI-->>Agents: TradeDecisionPayload
  Engine->>Risk: evaluate(decision, snapshot, limits)
  Risk-->>Engine: APPROVED / REJECTED / NEEDS_APPROVAL
  Engine->>DB: Persist agent run and trade decision
  alt AUTO_EXECUTE=true and risk approved and action is BUY/SELL
    Engine->>Broker: place_order(order)
    Broker-->>Engine: broker order result
    Engine->>DB: Persist order result
  else manual approval or HOLD
    Engine->>DB: Store decision without broker execution
  end
  Engine-->>API: DecisionResponse
  API-->>UI: Answer and artifacts
```

## Runtime Services

| Service     | Container               | Port   | Purpose                                        |
| ----------- | ----------------------- | ------ | ---------------------------------------------- |
| `postgres`  | `trade-pilot-postgres`  | `5432` | PostgreSQL database.                           |
| `backend`   | `trade-pilot-backend`   | `8000` | FastAPI backend and agent/risk/order services. |
| `admin-web` | `trade-pilot-admin-web` | `5173` | Admin dashboard.                               |
| `user-web`  | `trade-pilot-user-web`  | `5174` | User-facing analyst workspace.                 |

Start the full local stack:

```bash
docker compose up -d --build
```

If your local PostgreSQL volume was created before Alembic migrations were
enabled, the tables may already exist without an `alembic_version` row. For a
local disposable database, reset the volume before starting:

```bash
docker compose down -v
docker compose up -d --build
```

For a local database you want to keep, stamp the existing base schema once and
then apply the auth migration:

```bash
docker compose build backend
docker compose run --rm backend alembic stamp 0001_initial
docker compose run --rm backend alembic upgrade head
docker compose up -d
```

Open:

| App                  | URL                                |
| -------------------- | ---------------------------------- |
| User workspace       | `http://localhost:5174`            |
| Admin dashboard      | `http://localhost:5173`            |
| Backend health       | `http://localhost:8000/api/health` |
| Backend OpenAPI docs | `http://localhost:8000/docs`       |

Stop the stack:

```bash
docker compose down
```

## Local Development

| Component        | Commands                                                                                                                                                             |
| ---------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Backend          | `cd backend`<br/>`python -m venv .venv`<br/>`source .venv/bin/activate`<br/>`pip install -e ".[dev]"`<br/>`alembic upgrade head`<br/>`uvicorn app.main:app --reload` |
| User web         | `cd user-web`<br/>`npm install`<br/>`npm run dev`                                                                                                                    |
| Admin web        | `cd admin-web`<br/>`npm install`<br/>`npm run dev`                                                                                                                   |
| React Native app | `cd frontend`<br/>`npm install`<br/>`npm run start`                                                                                                                  |

## Hybrid Local Development

Use this mode when PostgreSQL runs in Docker, but backend and user-web run
directly on the host for faster iteration.

| Step                  | Command                                                                                       | What it uses                                                                                                         |
| --------------------- | --------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| Start DB only         | `docker compose up -d postgres`                                                               | `POSTGRES_PORT`, Docker volume `trade_pilot_pg`.                                                                     |
| Prepare backend once  | `cd backend && python3 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"` | Local Python virtual environment.                                                                                    |
| Run backend           | `./scripts/dev_backend.sh`                                                                    | Root `.env`, `DATABASE_URL`, `BACKEND_HOST`, `BACKEND_PORT`; applies `alembic upgrade head` before starting Uvicorn. |
| Prepare user-web once | `cd user-web && npm install`                                                                  | Local Node dependencies.                                                                                             |
| Run user-web          | `./scripts/dev_user_web.sh`                                                                   | Root `.env`, `USER_WEB_HOST`, `USER_WEB_PORT`, `VITE_API_BASE_URL`.                                                  |

The backend settings loader reads both the project root `.env` and
`backend/.env`; `backend/.env` can override root values for backend-only local
experiments. The Vite web configs use the project root `.env` via `envDir`, so
`VITE_API_BASE_URL` and web ports stay centralized.

If another local PostgreSQL process already listens on `127.0.0.1:5432`, expose
the Docker database on a different host port and point the backend at that port:

```bash
POSTGRES_PORT=5433
DATABASE_URL=postgresql+psycopg://trade_pilot:trade_pilot@localhost:5433/trade_pilot
```

## GitHub Publication Notes

| Area                 | Rule                                                                                                                               |
| -------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| Public documentation | The root `README.md` is the GitHub-facing overview and architecture document.                                                      |
| Admin notes          | `admin-web/README.md` is local-only and ignored by git. Keep environment-specific admin runbooks there instead of publishing them. |
| Secrets              | Do not commit `.env`, brokerage account numbers, gateway tokens, OpenAI keys, or production admin credentials.                     |
| Production hosting   | Build frontend static assets and serve them behind HTTPS; do not use Vite dev servers as production hosting.                       |
| Production cookies   | Set `APP_ENV=production`, `AUTH_COOKIE_SECURE=true`, and a non-default `ADMIN_PASSWORD`.                                           |

## Key API Surface

| Method | Path                             | Used by                             | Description                                                                                                                                                                |
| ------ | -------------------------------- | ----------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `GET`  | `/api/health`                    | All clients                         | Backend status and active broker mode.                                                                                                                                     |
| `GET`  | `/api/config`                    | User web, admin web                 | Public runtime config and risk limits.                                                                                                                                     |
| `POST` | `/api/auth/register`             | User web                            | Creates a regular user account when registration is enabled and starts a cookie session.                                                                                   |
| `POST` | `/api/auth/login`                | User web, admin web                 | Starts a server-side cookie session and returns a CSRF token plus `UserProfile`.                                                                                           |
| `POST` | `/api/auth/logout`               | User web, admin web                 | Revokes the current server-side session and clears auth cookies.                                                                                                           |
| `GET`  | `/api/auth/me`                   | User web, admin web                 | Validates the current session cookie and returns the authenticated user.                                                                                                   |
| `POST` | `/api/assistant/query`           | User web                            | Authenticated query-centered assistant workspace endpoint. Returns answer, skill coverage, artifacts, suggested actions, and optional decision scoped to the current user. |
| `POST` | `/api/decisions/run`             | Admin web, trading engine workflows | Runs a direct AI trade decision for the current user.                                                                                                                      |
| `GET`  | `/api/decisions`                 | User web, admin web                 | Lists the current user's recent AI decisions.                                                                                                                              |
| `GET`  | `/api/dashboard/summary`         | Admin web                           | Admin-role portfolio, PnL, order, and decision summary.                                                                                                                    |
| `GET`  | `/api/dashboard/transactions`    | Admin web                           | Admin-role recent order transaction view.                                                                                                                                  |
| `POST` | `/api/orders`                    | Admin web                           | Admin-role manual order staging in `PENDING_APPROVAL`.                                                                                                                     |
| `POST` | `/api/orders/{order_id}/approve` | User web, admin web                 | Sends the current user's pending order to the active broker.                                                                                                               |
| `GET`  | `/api/orders`                    | User web, admin web                 | Lists the current user's recent orders.                                                                                                                                    |
| `GET`  | `/api/positions`                 | User web, admin web                 | Lists the current user's positions.                                                                                                                                        |

## Assistant Artifacts

| Artifact type   | Rendered as                                              | Typical source                                                         |
| --------------- | -------------------------------------------------------- | ---------------------------------------------------------------------- |
| `metric_grid`   | Compact KPI grid                                         | System config, portfolio summary.                                      |
| `table`         | Data table                                               | Positions, orders, decisions, risk results, skill coverage.            |
| `line_chart`    | SVG line chart                                           | Synthetic paper-mode price context for a trade decision.               |
| `bar_chart`     | Horizontal bar chart                                     | Agent confidence or order status distribution.                         |
| `pie_chart`     | Allocation chart                                         | Portfolio market value allocation.                                     |
| `web_tab`       | Browser-style research card with an external open action | Research tab scaffold. Real web-search ingestion is not yet connected. |
| `decision_card` | Trading decision summary                                 | Action, symbol, quantity, confidence, risk status.                     |

## SKILLS Catalog

The prompt skill cards live in `backend/app/skills`. They are loaded by
`SkillCatalog` and injected into the assistant planner and trading agents.

| Skill file                    | Primary use                                                                                                   |
| ----------------------------- | ------------------------------------------------------------------------------------------------------------- |
| `index.md`                    | Global prompt rules for complete request solving, multi-skill selection, missing-skill reporting, and safety. |
| `system_status_and_config.md` | Backend health, broker mode, model config, and risk limits.                                                   |
| `market_snapshot.md`          | Quote source and `MarketSnapshot` construction.                                                               |
| `ai_trade_decision.md`        | AI trade decision workflow and required variables.                                                            |
| `risk_guardrails.md`          | Deterministic risk checks and execution boundaries.                                                           |
| `order_management.md`         | Manual orders, approval, broker execution, and order listing.                                                 |
| `portfolio_positions.md`      | Current holdings and market value views.                                                                      |
| `decision_history.md`         | Recent AI decisions and stored risk outcomes.                                                                 |
| `admin_dashboard.md`          | Admin-only summary, transactions, positions, and recent decisions.                                            |
| `auth_admin_session.md`       | User registration, cookie-session login, CSRF behavior, logout, and admin role boundaries.                    |
| `broker_adapters.md`          | Paper, direct CREON, and CREON gateway behavior.                                                              |
| `creon_gateway.md`            | Windows-native gateway requirements and endpoints.                                                            |

## Database Model

| Table             | Model           | Purpose                                                                                        |
| ----------------- | --------------- | ---------------------------------------------------------------------------------------------- |
| `users`           | `User`          | Stores normalized login identity, password hash, role, active state, and audit timestamps.     |
| `user_sessions`   | `UserSession`   | Stores hashes of opaque session and CSRF tokens, expiry, last-seen time, and revocation state. |
| `agent_runs`      | `AgentRun`      | Stores user-scoped raw request and agent payloads for each agent decision run.                 |
| `trade_decisions` | `TradeDecision` | Stores user-scoped structured AI decision, thesis, confidence, risk status, and raw payload.   |
| `orders`          | `Order`         | Stores user-scoped staged, approved, submitted, filled, or rejected orders.                    |
| `positions`       | `Position`      | Stores user-scoped symbol-level quantity, average price, and market price.                     |

## Configuration

Create a local `.env` file before running the backend outside Docker, or to
override Docker defaults.

| Variable                        | Default / example                                                         | Description                                                                                                                                     |
| ------------------------------- | ------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| `DATABASE_URL`                  | `postgresql+psycopg://trade_pilot:trade_pilot@localhost:5432/trade_pilot` | SQLAlchemy database URL. Docker overrides this to use the `postgres` service.                                                                   |
| `POSTGRES_HOST`                 | `127.0.0.1`                                                               | Hostname used by local tooling when PostgreSQL runs through Docker.                                                                             |
| `POSTGRES_PORT`                 | `5432`                                                                    | Host port exposed by the Docker PostgreSQL service.                                                                                             |
| `BACKEND_HOST`                  | `127.0.0.1`                                                               | Host used by `scripts/dev_backend.sh`. Docker overrides this to `0.0.0.0` inside the backend container.                                         |
| `BACKEND_PORT`                  | `8000`                                                                    | Backend Uvicorn port for local scripts and Docker Compose port mapping.                                                                         |
| `BACKEND_BASE_URL`              | `http://localhost:8000`                                                   | Human-readable local backend base URL.                                                                                                          |
| `USER_WEB_HOST`                 | `127.0.0.1`                                                               | Host used by the user-web Vite dev server.                                                                                                      |
| `USER_WEB_PORT`                 | `5174`                                                                    | User-web Vite dev server port and backend CORS origin source.                                                                                   |
| `ADMIN_WEB_HOST`                | `127.0.0.1`                                                               | Host used by the admin-web Vite dev server.                                                                                                     |
| `ADMIN_WEB_PORT`                | `5173`                                                                    | Admin-web Vite dev server port and backend CORS origin source.                                                                                  |
| `VITE_API_BASE_URL`             | `http://localhost:8000`                                                   | Browser-facing backend URL consumed by Vite web apps.                                                                                           |
| `OPENAI_API_KEY`                | unset                                                                     | Enables real OpenAI planner and agent calls. Without it, trade decisions fall back to conservative `HOLD`; planner uses deterministic matching. |
| `OPENAI_MODEL`                  | `gpt-5.4-mini`                                                            | Model name passed to LangChain `ChatOpenAI`.                                                                                                    |
| `ADMIN_USERNAME`                | `admin`                                                                   | Bootstrap admin username.                                                                                                                       |
| `ADMIN_PASSWORD`                | `change-me-now`                                                           | Bootstrap admin password. Change for any non-local environment. The default is refused in production.                                           |
| `SESSION_TTL_MINUTES`           | `720`                                                                     | Server-side session and cookie expiry window.                                                                                                   |
| `PASSWORD_HASH_ITERATIONS`      | `390000`                                                                  | PBKDF2-SHA256 iterations for password hashing.                                                                                                  |
| `SESSION_COOKIE_NAME`           | `trade_pilot_session`                                                     | HttpOnly session cookie name.                                                                                                                   |
| `CSRF_COOKIE_NAME`              | `trade_pilot_csrf`                                                        | Readable CSRF cookie name used by web clients for `X-CSRF-Token`.                                                                               |
| `AUTH_COOKIE_SECURE`            | `false`                                                                   | Set to `true` when served over HTTPS.                                                                                                           |
| `AUTH_COOKIE_SAMESITE`          | `lax`                                                                     | Session and CSRF cookie SameSite policy.                                                                                                        |
| `ALLOW_USER_REGISTRATION`       | `true`                                                                    | Enables or disables public regular-user registration.                                                                                           |
| `BROKER_MODE`                   | `paper`                                                                   | One of `paper`, `creon`, or `creon_gateway`.                                                                                                    |
| `AUTO_EXECUTE`                  | `false`                                                                   | If true, approved BUY/SELL decisions can create broker orders automatically.                                                                    |
| `ALLOW_LIVE_TRADING`            | `false`                                                                   | Required live-trading gate.                                                                                                                     |
| `I_UNDERSTAND_LOSS_RISK`        | `false`                                                                   | Required live-trading gate.                                                                                                                     |
| `MAX_ORDER_KRW`                 | `500000`                                                                  | Max notional per executable decision.                                                                                                           |
| `MAX_POSITION_KRW`              | `1000000`                                                                 | Max position notional.                                                                                                                          |
| `MAX_DAILY_LOSS_KRW`            | `200000`                                                                  | Reserved daily loss cap setting.                                                                                                                |
| `MIN_DECISION_CONFIDENCE`       | `0.62`                                                                    | Minimum confidence for executable decisions.                                                                                                    |
| `CREON_ACCOUNT_NO`              | unset                                                                     | Required for direct CREON or gateway live orders.                                                                                               |
| `CREON_GOODS_CODE`              | `01`                                                                      | CREON account goods code.                                                                                                                       |
| `CREON_GATEWAY_URL`             | `http://127.0.0.1:8765`                                                   | Windows gateway base URL.                                                                                                                       |
| `CREON_GATEWAY_TOKEN`           | unset                                                                     | Optional shared token sent as `x-trade-pilot-token`.                                                                                            |
| `CREON_GATEWAY_TIMEOUT_SECONDS` | `10`                                                                      | HTTP timeout for gateway calls.                                                                                                                 |

## Safety Boundaries

| Boundary                      | Enforcement                                                                                                                             |
| ----------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| User isolation                | Authenticated routes scope decisions, orders, and positions to the current `users.id`.                                                  |
| Session security              | Browser auth uses opaque HttpOnly session cookies, server-side token hashes, CSRF double-submit verification, and revocable sessions.   |
| Admin access                  | Admin dashboard summary, transactions, and manual order staging require `role=admin`.                                                   |
| Default paper mode            | `BROKER_MODE=paper`; Docker backend also sets `BROKER_MODE=paper`.                                                                      |
| Live trading opt-in           | Requires `BROKER_MODE` of `creon` or `creon_gateway`, `ALLOW_LIVE_TRADING=true`, and `I_UNDERSTAND_LOSS_RISK=true`.                     |
| Model cannot execute directly | OpenAI produces structured decisions only. `TradingEngine` and `RiskManager` decide whether an order can be created.                    |
| Risk gate                     | Rejects low confidence, invalid quantity, oversized notional, position-limit breach, unapproved live mode, or requested human approval. |
| Manual approval               | `AUTO_EXECUTE=false` means decisions do not create broker orders automatically. Manual orders are staged as `PENDING_APPROVAL`.         |
| Missing skills                | The assistant planner reports missing provider/integration skills instead of inventing endpoints or data.                               |

## Auth Flow

| Step                | Component                    | Behavior                                                                                                                                                 |
| ------------------- | ---------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Register            | `POST /api/auth/register`    | Creates a regular `user` account when `ALLOW_USER_REGISTRATION=true`, hashes the password, creates a server-side session, and sets session/CSRF cookies. |
| Login               | `POST /api/auth/login`       | Authenticates an existing user. The configured admin credentials bootstrap an `admin` user on first successful login.                                    |
| Session validation  | `GET /api/auth/me`           | Reads the HttpOnly session cookie, verifies the stored token hash, expiry, revocation state, and active user.                                            |
| CSRF protection     | unsafe authenticated methods | Requires `X-CSRF-Token` to match the readable CSRF cookie and the server-side CSRF token hash.                                                           |
| Logout              | `POST /api/auth/logout`      | Revokes the current session row and clears auth cookies.                                                                                                 |
| Admin authorization | admin dashboard routes       | Requires a valid session plus `role=admin`.                                                                                                              |

## CREON Plus Constraints

CREON Plus / CYBOS Plus is a Windows COM API. Direct live trading requires:

| Requirement                        | Reason                                                                |
| ---------------------------------- | --------------------------------------------------------------------- |
| Windows host or Windows VM         | CREON Plus depends on Windows COM and an interactive HTS login state. |
| 32-bit Python caller               | CREON Plus COM callers must be 32-bit.                                |
| `pywin32`                          | Required for COM dispatch.                                            |
| CREON Plus installed and logged in | Quote/order COM objects depend on the local logged-in session.        |
| Explicit live gates                | Backend refuses live mode unless loss-risk approvals are enabled.     |

Run the gateway on Windows:

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

Point the backend at the gateway:

```bash
BROKER_MODE=creon_gateway
CREON_GATEWAY_URL=http://WINDOWS_VM_IP:8765
CREON_GATEWAY_TOKEN=change-me
ALLOW_LIVE_TRADING=true
I_UNDERSTAND_LOSS_RISK=true
```

## Validation

| Check                              | Command                                                                                                                                                                                                                                                                                                       |
| ---------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Backend syntax                     | `python3 -m py_compile backend/app/core/config.py backend/app/core/auth.py backend/app/models.py backend/app/schemas.py backend/app/api/routes.py backend/app/services/trading_engine.py backend/app/services/assistant_workspace.py backend/app/main.py backend/alembic/versions/0002_user_auth_sessions.py` |
| Backend tests                      | `env PYTHONPATH=backend backend/.venv/bin/pytest backend/tests`                                                                                                                                                                                                                                               |
| User web typecheck                 | `npm run typecheck --prefix user-web`                                                                                                                                                                                                                                                                         |
| User web build                     | `npm run build --prefix user-web`                                                                                                                                                                                                                                                                             |
| Admin web typecheck                | `npm run typecheck --prefix admin-web`                                                                                                                                                                                                                                                                        |
| Admin web build                    | `npm run build --prefix admin-web`                                                                                                                                                                                                                                                                            |
| Backend health                     | `curl http://127.0.0.1:8000/api/health`                                                                                                                                                                                                                                                                       |
| Authenticated assistant smoke test | Register or log in through `user-web`, then run a query from the browser so cookies and CSRF are sent automatically.                                                                                                                                                                                          |

Trade-pilot is engineering scaffolding, not financial advice. Test in paper mode
with small mock limits before connecting any real brokerage account.
