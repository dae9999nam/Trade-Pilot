# Skill: Market Snapshot

## Purpose

Use this skill to understand how Trade-pilot obtains the price context for a
decision. The market snapshot is the price input that downstream agents and
`RiskManager` use.

## When to use

- User asks for a decision and provides a current or assumed price.
- User asks why a specific price was used.
- User asks for quote retrieval behavior in paper, CREON, or gateway mode.

## Backend service

`MarketDataService.snapshot_for(request: DecisionRequest) -> MarketSnapshot`

Operation:

| Condition | Behavior |
| --- | --- |
| `request.last_price` is provided | Return a `MarketSnapshot` using that price and `source="request"`. |
| `request.last_price` is omitted | Ask the active broker adapter for `get_quote(symbol)`. |

## Input variables

| Variable | Type | Required | Notes |
| --- | --- | --- | --- |
| `symbol` | string | yes | 2 to 16 chars. Converted to uppercase by the backend. |
| `last_price` | decimal | no | Must be greater than or equal to 0. If present, broker quote lookup is skipped. |

## Output variables

| Field | Type | Meaning |
| --- | --- | --- |
| `symbol` | string | Uppercase symbol. |
| `price` | decimal | Price used for decision and risk notional calculation. |
| `open_price` | decimal or null | Opening price if broker provides it. |
| `high_price` | decimal or null | High price if broker provides it. |
| `low_price` | decimal or null | Low price if broker provides it. |
| `volume` | integer or null | Volume if broker provides it. |
| `source` | string | `request`, `paper`, `creon`, or `creon_gateway`. |

## Related broker behavior

| Broker mode | Quote behavior |
| --- | --- |
| `paper` | Returns deterministic synthetic quote data from `PaperBroker`. |
| `creon` | Reads quote data through CREON Plus COM on Windows 32-bit Python. |
| `creon_gateway` | Calls the Windows gateway `GET /quote/{symbol}` endpoint. |

## Safety notes

- A user-provided `last_price` is trusted as a request snapshot. If precision is
  critical, ask the user to confirm the price or use broker quote retrieval.
- The snapshot does not execute orders.
