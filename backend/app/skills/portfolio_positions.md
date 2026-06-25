# Skill: Portfolio Positions

## Purpose

Use this skill when the user asks for current holdings, position quantities,
average price, market price, or portfolio market value.

## Endpoint

`GET /api/positions`

Lists all positions sorted by symbol.

For live account comparison, use `GET /api/account/reconciliation` from
`account_reconciliation.md` instead of relying on stored positions alone.

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
| Live CREON order | Stored positions must be compared with broker snapshots through account reconciliation. |

## Safety notes

- `positions` reflect the application's stored state.
- For live trading, check `account_reconciliation.md` and do not claim broker
  holdings are synchronized unless `broker_status` is `SYNCED` and rows match.
