# Skill: Decision History

## Purpose

Use this skill when the user asks for recent AI decisions, past risk outcomes,
recent symbols reviewed by agents, or decision audit context.

## Endpoint

`GET /api/decisions`

Lists up to 50 recent `TradeDecision` rows, newest first.

## Output variables

| Field | Type | Meaning |
| --- | --- | --- |
| `id` | integer | Decision ID. |
| `symbol` | string | Stock symbol. |
| `action` | `BUY` / `SELL` / `HOLD` | Final supervisor action. |
| `quantity` | integer | Final proposed quantity. |
| `confidence` | number | Final supervisor confidence. |
| `risk_status` | `APPROVED` / `REJECTED` / `NEEDS_APPROVAL` | Deterministic risk outcome. |
| `risk_reasons` | array of strings | Reasons returned by `RiskManager`. |
| `created_at` | datetime | Decision creation timestamp. |

## Storage source

Data comes from the `trade_decisions` table. The raw structured payload is stored
internally on the row as `raw_payload`, but this endpoint returns a compact view.

## Safety notes

- Decision history is audit context only.
- A past approved decision should not be reused as a new order without fresh
  market data and risk evaluation.
