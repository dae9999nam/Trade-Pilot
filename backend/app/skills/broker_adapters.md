# Skill: Broker Adapters

## Purpose

Use this skill when selecting or explaining the active broker, quote source, or
order submission path.

## Broker selection

`app.broker.factory.get_broker()` selects an implementation using
`settings.broker_mode`.

| `BROKER_MODE` | Adapter | Quote behavior | Order behavior |
| --- | --- | --- | --- |
| `paper` | `PaperBroker` | Deterministic synthetic quote from symbol hash. | Immediately returns `FILLED` with a `PAPER-*` broker order ID. |
| `creon` | `CreonBroker` | CREON Plus COM `DsCbo1.StockMst`. | CREON Plus COM `CpTrade.CpTd0311`. |
| `creon_gateway` | `CreonGatewayBroker` | HTTP `GET /quote/{symbol}` on Windows gateway. | HTTP `POST /orders` on Windows gateway. |

## Common broker order shape

`BrokerOrder`

| Field | Type | Meaning |
| --- | --- | --- |
| `symbol` | string | Stock symbol. |
| `side` | `BUY` / `SELL` | Direction. |
| `quantity` | integer | Number of shares. |
| `order_type` | `MARKET` / `LIMIT` | Order type. |
| `limit_price` | decimal or null | Limit price when applicable. |

`BrokerOrderResult`

| Field | Type | Meaning |
| --- | --- | --- |
| `broker_order_id` | string or null | External broker order ID. |
| `status` | string | Broker submission status. |
| `message` | string | Broker or adapter message. |

## Live trading requirements

| Requirement | Applies to |
| --- | --- |
| Windows OS | Direct `creon`; gateway process |
| 32-bit Python | Direct `creon`; gateway process |
| CREON Plus installed and logged in | Direct `creon`; gateway process |
| `ALLOW_LIVE_TRADING=true` | Direct `creon`; gateway mode |
| `I_UNDERSTAND_LOSS_RISK=true` | Direct `creon`; gateway mode |
| `CREON_ACCOUNT_NO` configured | Live order placement |

## Safety notes

- Default broker mode is `paper`.
- The default Docker Compose stack intentionally forces `BROKER_MODE=paper`.
- Use `docker-compose.creon-gateway.yml` only when a Windows CREON gateway is
  already running and live-trading gates are explicitly enabled.
- A Windows container image is only a gateway packaging scaffold. It does not
  automatically inherit the host CREON Plus COM registration or logged-in HTS
  session.
- Prefer the direct Windows host gateway process when the backend runs on
  macOS/Linux and live trading must be delegated to a Windows host.
