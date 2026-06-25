# Trade-pilot Skill Catalog

This directory contains Markdown skill cards intended to be injected into the
OpenAI prompts used by `AgentOrchestrator` and the assistant workspace planner.

## How the model should use these skills

1. Read the full user query and identify the complete outcome the user needs.
2. Do not collapse the request into one intent label. Decompose it into every
   task needed to answer or solve it.
3. Select every existing skill card required for those tasks.
4. If a required skill, endpoint, provider, integration, variable, or artifact
   is missing, explain exactly what is missing instead of inventing it.
5. Extract required variables before proposing or executing an action.
6. Prefer read-only skills for informational queries.
7. Use trading skills only when the user explicitly asks for a decision, order,
   approval, position review, or account action.
8. Never invent an endpoint, field, enum value, broker mode, or order status
   that is not described in these files.
9. Never bypass `RiskManager`, human approval requirements, or live-trading
   environment gates.

## Available skills

| Skill file | Primary use |
| --- | --- |
| `system_status_and_config.md` | Read backend health, broker mode, model config, and risk limits. |
| `market_snapshot.md` | Understand how quotes and request-provided prices become `MarketSnapshot`. |
| `ai_trade_decision.md` | Run or reason about AI trade decisions through `/api/decisions/run`. |
| `risk_guardrails.md` | Explain deterministic risk checks and why decisions are approved or rejected. |
| `order_management.md` | Stage manual orders, approve or retry approvable orders, list orders, and inspect lifecycle events. |
| `portfolio_positions.md` | Read current holdings and portfolio position values. |
| `account_reconciliation.md` | Compare application positions with broker account snapshots and explain sync gaps. |
| `decision_history.md` | Read recent AI decisions and their risk outcomes. |
| `admin_dashboard.md` | Read admin-only account summary and transaction views. |
| `auth_admin_session.md` | Register users, authenticate cookie sessions, validate identity, and enforce admin role boundaries. |
| `broker_adapters.md` | Select and reason about paper, direct CREON, and gateway broker modes. |
| `creon_gateway.md` | Use the Windows-native CREON gateway quote and order APIs. |

## Global safety rules

- Default to paper trading unless the environment explicitly enables live
  trading.
- Live trading requires `ALLOW_LIVE_TRADING=true`,
  `I_UNDERSTAND_LOSS_RISK=true`, and broker mode `creon` or `creon_gateway`.
- A trade recommendation is not the same thing as an executable order.
- `BUY` and `SELL` actions require positive quantity and deterministic risk
  approval before execution.
- `HOLD` is always acceptable when evidence is weak, market data is missing, or
  user intent is unclear.
- If a user asks for an order but omits required fields, ask for the missing
  fields instead of guessing.
- Authenticated web clients must use server-side cookie sessions with CSRF
  protection. Do not invent bearer-token or JWT behavior.
