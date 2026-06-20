# Skill: Portfolio Positions

## Purpose

Use this skill when the user asks for current holdings, position quantities,
average price, market price, or portfolio market value.

## Endpoint

`GET /api/positions`

Lists all positions sorted by symbol.

## Output variables

Response body: array of `PositionView`

| Field | Type | Meaning |
| --- | --- | --- |
| `symbol` | string | Stock symbol. |
| `quantity` | integer | Current share quantity. |
| `avg_price` | decimal | Average cost basis used by the system. |
| `market_price` | decimal | Latest stored market price. |

## Position update behavior

| Event | Behavior |
| --- | --- |
| Paper order `FILLED` | `TradingEngine._upsert_paper_position` updates the stored position. |
| Buy order | Increases quantity and recalculates average price. |
| Sell order | Decreases quantity and preserves the existing average price while shares remain. If quantity falls to or below zero, stored quantity becomes `0`. |
| Live CREON order | Current backend does not reconcile live broker holdings into `positions`. |

## Safety notes

- `positions` reflect the application's stored state, not necessarily a live
  broker account reconciliation.
- For live trading, confirm actual broker positions through CREON or account
  systems before making high-stakes decisions.
