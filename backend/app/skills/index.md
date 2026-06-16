# Trade-pilot Skill Catalog

This directory contains Markdown skill cards intended to be injected into the
OpenAI prompt used by `AgentOrchestrator`.

## How the model should use these skills

1. Read the user query and classify the intent.
2. Select only the skill cards that match the intent.
3. Extract required variables before proposing or executing an action.
4. Prefer read-only skills for informational queries.
5. Use trading skills only when the user explicitly asks for a decision, order,
   approval, position review, or account action.
6. Never invent an endpoint, field, enum value, broker mode, or order status
   that is not described in these files.
7. Never bypass `RiskManager`, human approval requirements, or live-trading
   environment gates.

## Available skills

| Skill file | Primary use |
| --- | --- |
| `system_status_and_config.md` | Read backend health, broker mode, model config, and risk limits. |
| `market_snapshot.md` | Understand how quotes and request-provided prices become `MarketSnapshot`. |
| `ai_trade_decision.md` | Run or reason about AI trade decisions through `/api/decisions/run`. |
| `risk_guardrails.md` | Explain deterministic risk checks and why decisions are approved or rejected. |
| `order_management.md` | Stage manual orders, approve pending orders, and list orders. |
| `portfolio_positions.md` | Read current holdings and portfolio position values. |
| `decision_history.md` | Read recent AI decisions and their risk outcomes. |
| `admin_dashboard.md` | Read admin-only account summary and transaction views. |
| `auth_admin_session.md` | Authenticate admin dashboard requests and validate bearer tokens. |
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
