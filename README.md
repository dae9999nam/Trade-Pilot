# Trade-pilot

Trade-pilot is a full-stack trading assistant for Korean equities. It combines
an analyst-style React web workspace, a FastAPI backend, OpenAI-powered agent
workflows, deterministic risk controls, paper trading, and optional CREON
Plus integration through a Windows gateway.

The project is designed as trading infrastructure scaffolding. It is not
financial advice, and live brokerage access is disabled by default.

## What It Does

| Area                   | Functionality                                                                                                                                        |
| ---------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| AI assistant workspace | Users ask natural-language trading or portfolio questions and receive structured responses, not just chat text.                                      |
| Multi-artifact answers | Responses can include text, metrics, tables, line charts, bar charts, pie charts, decision cards, and browser-style research tabs.                   |
| Skill-aware planning   | The assistant inspects Markdown skill cards before choosing which internal capability to use. Missing capabilities are reported instead of invented. |
| AI trade decisions     | Specialist agents and a supervisor produce structured BUY, SELL, or HOLD decisions.                                                                  |
| Risk controls          | Deterministic checks enforce confidence thresholds, position limits, order size limits, human approval, and live-trading gates.                      |
| Paper trading          | The default broker is a safe paper adapter for local testing.                                                                                        |
| CREON Plus integration | Optional Windows-native gateway can bridge to CREON Plus / CYBOS Plus COM APIs.                                                                      |
| Authenticated web app  | Browser clients use server-side sessions, HttpOnly cookies, CSRF protection, and user-scoped data.                                                   |
| Admin console          | Admin users can inspect dashboard summaries, positions, recent decisions, transactions, and orders.                                                  |

## Applications

| App           | Path        | Purpose                                                                         |
| ------------- | ----------- | ------------------------------------------------------------------------------- |
| User web      | `user-web`  | Main analyst workspace for user-facing requests.                                |
| Admin web     | `admin-web` | Admin dashboard for operations, review, and manual order flow.                  |
| Backend       | `backend`   | FastAPI API, auth, agent orchestration, risk, persistence, and broker adapters. |
| CREON gateway | `gateway`   | Windows-native FastAPI gateway that owns CREON Plus COM calls.                  |
| Legacy mobile | `frontend`  | React Native / Expo app retained while the user-facing experience moves to web. |

## System Architecture

```mermaid
flowchart LR
  User["User"] --> UserWeb["user-web<br/>React analyst workspace"]
  Admin["Admin"] --> AdminWeb["admin-web<br/>Operations dashboard"]
  Mobile["Legacy mobile app"] --> MobileApp["frontend<br/>React Native / Expo"]

  UserWeb --> API["FastAPI backend<br/>/api"]
  AdminWeb --> API
  MobileApp --> API

  API --> Auth["Auth<br/>HttpOnly session + CSRF"]
  API --> Assistant["AssistantWorkspace<br/>request planner"]
  API --> Engine["TradingEngine<br/>decisions + orders"]
  API --> DB["PostgreSQL"]

  Assistant --> Skills["SKILLS catalog<br/>Markdown capability cards"]
  Assistant --> DB
  Assistant --> Engine
  Assistant --> Artifacts["UI artifacts<br/>tables + charts + cards"]

  Engine --> Orchestrator["AgentOrchestrator<br/>specialists + supervisor"]
  Orchestrator --> Skills
  Orchestrator --> OpenAI["OpenAI API"]
  Engine --> Risk["RiskManager<br/>deterministic guardrails"]
  Engine --> BrokerFactory["Broker factory"]
  Engine --> DB

  BrokerFactory --> Paper["PaperBroker"]
  BrokerFactory --> CreonDirect["CreonBroker<br/>Windows COM"]
  BrokerFactory --> CreonGatewayBroker["CreonGatewayBroker<br/>HTTP client"]
  CreonGatewayBroker --> Gateway["Windows CREON Gateway"]
  Gateway --> Creon["CREON Plus / CYBOS Plus<br/>32-bit COM"]
```

## Assistant Flow

```mermaid
flowchart TD
  Query["User query"] --> Planner["Assistant planner"]
  Planner --> Objective["Define complete objective"]
  Objective --> SkillCatalog["Inspect SKILLS catalog"]
  SkillCatalog --> ExistingSkills["Select available skills"]
  SkillCatalog --> MissingSkills["Report missing skills"]
  ExistingSkills --> Capabilities["Run needed capabilities"]

  Capabilities --> Status["system_status"]
  Capabilities --> Portfolio["portfolio_review"]
  Capabilities --> Orders["order_review"]
  Capabilities --> History["decision_history"]
  Capabilities --> Research["web_research tab scaffold"]
  Capabilities --> Decision["trade_decision"]

  Status --> Response["AssistantQueryResponse"]
  Portfolio --> Response
  Orders --> Response
  History --> Response
  Research --> Response
  Decision --> Response
  MissingSkills --> Response

  Response --> UI["Rendered answer<br/>text + artifacts"]
```

## Trading Decision Flow

```mermaid
sequenceDiagram
  participant UI as Web UI
  participant API as FastAPI
  participant Market as MarketDataService
  participant Engine as TradingEngine
  participant Agents as AgentOrchestrator
  participant Risk as RiskManager
  participant DB as PostgreSQL
  participant Broker as Broker adapter

  UI->>API: POST /api/assistant/query or /api/decisions/run
  API->>Market: Build market snapshot
  Market->>Broker: Get quote unless last_price was provided
  API->>Engine: Run decision
  Engine->>Agents: Specialist agents + supervisor
  Agents-->>Engine: Structured trade decision
  Engine->>Risk: Apply deterministic guardrails
  Risk-->>Engine: APPROVED / REJECTED / NEEDS_APPROVAL
  Engine->>DB: Persist agent run and decision
  alt Auto execution enabled and risk approved
    Engine->>Broker: Submit order
    Broker-->>Engine: Broker result
    Engine->>DB: Persist order result
  else Hold or manual approval required
    Engine->>DB: Store decision without broker execution
  end
  Engine-->>API: Decision response
  API-->>UI: Answer and artifacts
```

## Core Components

| Component            | Responsibility                                                                                                          |
| -------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| `AssistantWorkspace` | Plans a user request as a full objective, selects needed capabilities, and returns a multi-artifact workspace response. |
| `AgentOrchestrator`  | Uses OpenAI and the SKILLS catalog to run trading specialists and produce a structured decision.                        |
| `TradingEngine`      | Persists agent runs and decisions, invokes risk checks, and coordinates order creation or approval.                     |
| `RiskManager`        | Enforces non-negotiable safety boundaries outside the language model.                                                   |
| `PaperBroker`        | Provides deterministic paper-mode quote/order behavior for development.                                                 |
| `CreonGatewayBroker` | Calls the Windows gateway over HTTP for CREON quote and order operations.                                               |
| `gateway`            | Runs on Windows and owns CREON Plus COM interaction.                                                                    |
| `PostgreSQL`         | Stores users, sessions, decisions, agent payloads, orders, and positions.                                               |

## Runtime Services

| Service       | Default URL / Port                             | Notes                                    |
| ------------- | ---------------------------------------------- | ---------------------------------------- |
| User web      | `http://localhost:5174`                        | Main user-facing web app.                |
| Admin web     | `http://localhost:5173`                        | Admin operations dashboard.              |
| Backend API   | `http://localhost:8000`                        | FastAPI routes and OpenAPI docs.         |
| PostgreSQL    | `localhost:5432` or configured `POSTGRES_PORT` | Docker-backed local database.            |
| CREON gateway | `http://WINDOWS_HOST:8765`                     | Optional Windows service for CREON Plus. |

## Quick Start

Create a local `.env` file with at least your OpenAI key and local admin
credentials. Keep `.env` out of git.

```bash
OPENAI_API_KEY=your-openai-key
OPENAI_MODEL=gpt-5.4-mini
ADMIN_USERNAME=admin
ADMIN_PASSWORD=change-this-password
```

Start the default paper-trading stack:

```bash
docker compose up --build -d
```

Open:

| Surface         | URL                                |
| --------------- | ---------------------------------- |
| User workspace  | `http://localhost:5174`            |
| Admin dashboard | `http://localhost:5173`            |
| Backend health  | `http://localhost:8000/api/health` |
| Backend docs    | `http://localhost:8000/docs`       |

For development workflows, local execution, testing, and CREON setup details,
see [README_dev.md](./README_dev.md).

## CREON Plus Integration

CREON Plus is Windows-only and COM-based. The recommended live topology is to
run the main app stack normally and run the CREON gateway on a separate Windows
host or VM where CREON Plus is installed and logged in.

| Requirement                        | Why it matters                                                            |
| ---------------------------------- | ------------------------------------------------------------------------- |
| Windows host or VM                 | CREON Plus depends on Windows COM and an interactive desktop login state. |
| 32-bit Python process              | CREON Plus COM APIs require a 32-bit caller.                              |
| CREON Plus installed and logged in | Quote and order COM objects depend on the active HTS session.             |
| Explicit live gates                | Backend refuses live mode unless risk acknowledgements are enabled.       |

`docker compose up --build -d` does not create a Windows VM, install CREON
Plus, or complete brokerage login. Those steps must be handled on the Windows
machine. The repository includes helper scripts for preparing the Python
gateway runtime after CREON Plus is installed.

## Safety Boundaries

| Boundary            | Enforcement                                                                                                            |
| ------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| Default paper mode  | The standard Docker stack runs `BROKER_MODE=paper`.                                                                    |
| Live trading opt-in | Requires `BROKER_MODE=creon` or `creon_gateway`, `ALLOW_LIVE_TRADING=true`, and `I_UNDERSTAND_LOSS_RISK=true`.         |
| Model boundary      | OpenAI can propose structured decisions, but it cannot submit orders directly.                                         |
| Risk gate           | Backend rejects invalid quantity, low confidence, oversized notional, position-limit breach, and unapproved live mode. |
| Auth boundary       | User routes are session-authenticated and scoped to the current user.                                                  |
| Admin boundary      | Dashboard summaries, transaction views, manual order staging, and approvals require admin role.                        |
| Manual approval     | `AUTO_EXECUTE=false` prevents AI decisions from creating broker orders automatically.                                  |

## Repository Layout

```text
Trade-pilot/
  backend/                  FastAPI backend, agents, risk, DB models, broker adapters
  user-web/                 React/Vite user workspace
  admin-web/                React/Vite admin dashboard
  frontend/                 Legacy React Native / Expo app
  gateway/                  Windows CREON Plus gateway
  backend/app/skills/       Markdown skills injected into assistant prompts
  infra/windows/            Windows gateway setup helper
  scripts/                  Local development helper scripts
  docker-compose.yml        Default paper-mode local stack
  docker-compose.creon-gateway.yml
  docker-compose.windows.yml
```

## Status

Trade-pilot is an engineering scaffold for a trading assistant and broker
integration workflow. Treat live trading as a separate production-hardening
project: validate paper mode first, keep limits small, add broker reconciliation
and audit logging, and do not enable automatic execution until the full order
lifecycle is proven end to end.
