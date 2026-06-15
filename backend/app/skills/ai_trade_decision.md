# Skill: AI Trade Decision

## Purpose

Use this skill when the user asks for an AI trading decision, agent review,
buy/sell/hold recommendation, or structured trade proposal for a stock symbol.

## Backend endpoint

`POST /api/decisions/run`

This endpoint builds a market snapshot, asks `AgentOrchestrator` for a
structured decision, evaluates it through `RiskManager`, persists the run and
decision, and optionally creates an order when auto-execution is enabled.

## Input variables

Request body: `DecisionRequest`

| Field | Type | Required | Validation | Meaning |
| --- | --- | --- | --- | --- |
| `symbol` | string | yes | length 2 to 16 | Stock symbol, converted to uppercase. |
| `quantity` | integer | no | `>= 0`, default `1` | Requested quantity for a possible trade. |
| `max_position_krw` | integer or null | no | `>= 0` | Optional per-request position cap overriding the default. |
| `last_price` | decimal or null | no | `>= 0` | Optional user-provided price snapshot. |
| `notes` | string or null | no | max 2000 chars | Extra user context for the decision request. |

## Output variables

Response body: `DecisionResponse`

| Field | Type | Meaning |
| --- | --- | --- |
| `id` | integer | Database ID of the persisted trade decision. |
| `risk_status` | `APPROVED` / `REJECTED` / `NEEDS_APPROVAL` | Deterministic risk result. |
| `risk_reasons` | array of strings | Reasons produced by `RiskManager`. |
| `decision` | `TradeDecisionPayload` | Structured AI decision. |
| `order_id` | integer or null | Created order ID when auto-execution creates an order. |

`TradeDecisionPayload` fields:

| Field | Type | Meaning |
| --- | --- | --- |
| `symbol` | string | Uppercase symbol. |
| `action` | `BUY` / `SELL` / `HOLD` | Proposed action. |
| `quantity` | integer | Proposed quantity. Must be positive for executable `BUY` or `SELL`. |
| `order_type` | `MARKET` / `LIMIT` | Proposed order type. |
| `limit_price` | decimal or null | Required for meaningful limit orders. |
| `confidence` | number | 0 to 1 model confidence. |
| `thesis` | string | Short rationale for the decision. |
| `stop_loss_pct` | number or null | Suggested stop-loss percentage. |
| `take_profit_pct` | number or null | Suggested take-profit percentage. |
| `require_human_approval` | boolean | Whether the AI asks for human approval. |
| `agent_votes` | array of `AgentVerdict` | Specialist agent outputs. |

## Agent behavior

`AgentOrchestrator` runs four specialist roles before the supervisor:

| Role | Focus |
| --- | --- |
| `market_analyst` | Market direction, quote quality, immediate signal strength. |
| `risk_analyst` | Sizing, downside, stop logic, reasons to block. |
| `portfolio_analyst` | Exposure and requested quantity coherence. |
| `execution_analyst` | Order type, limit price, execution feasibility. |

If `OPENAI_API_KEY` is missing, the orchestrator returns a safe `HOLD`
decision with confidence `0.0`.

## When to ask follow-up questions

Ask the user for missing data when:

| Missing data | Why it matters |
| --- | --- |
| `symbol` | The backend cannot build a request without it. |
| Intended quantity | Default is `1`, but user intent may require a different size. |
| Price confidence | If no `last_price` is supplied, the active broker quote will be used. |
| Live-trading intent | Live trading requires explicit environment gates and should not be assumed. |

## Safety notes

- A model decision is not a direct order unless `AUTO_EXECUTE=true`, risk status
  is `APPROVED`, and action is `BUY` or `SELL`.
- Prefer `HOLD` when evidence is thin or user intent is unclear.
- Do not fabricate agent votes or risk reasons; use the returned payload.
