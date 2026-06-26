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

`BrokerOrderStatusResult`

| Field | Type | Meaning |
| --- | --- | --- |
| `broker_order_id` | string or null | External broker order ID. |
| `status` | string | Broker-observed order status. |
| `message` | string | Broker or adapter message. |
| `filled_quantity` | integer or null | Filled quantity when the broker provides it. |
| `remaining_quantity` | integer or null | Remaining open quantity when available. |
| `as_of` | datetime or null | Broker/gateway observation timestamp. |
| `raw_payload` | object or null | Broker-specific diagnostic payload. |

`BrokerAccountSnapshot`

| Field | Type | Meaning |
| --- | --- | --- |
| `source` | string | Broker snapshot source. |
| `cash_krw` | decimal or null | Broker cash balance when the adapter supports it. |
| `positions` | array | Broker account positions. |
| `as_of` | datetime or null | Broker/gateway observation timestamp. |
| `raw_payload` | object or null | Broker-specific diagnostic payload. |

Order status refresh and cancellation:

| Broker mode | Status refresh | Cancel |
| --- | --- | --- |
| `paper` | Supported for local/demo orders. | Supported for local/demo orders. |
| `creon` | Not implemented in direct adapter. | Not implemented in direct adapter. |
| `creon_gateway` | Calls gateway `GET /orders/{broker_order_id}`. Gateway currently returns not-implemented until CREON COM mapping is added. | Calls gateway `POST /orders/{broker_order_id}/cancel`. Gateway currently returns not-implemented until CREON COM mapping is added. |

Account snapshots:

| Broker mode | Account snapshot |
| --- | --- |
| `paper` | Account reconciliation uses the application database as the paper ledger. |
| `creon` | Not implemented in direct adapter. |
| `creon_gateway` | Calls gateway `GET /account`, which maps CREON holdings through `CpTrade.CpTd6033`. |

## Live trading requirements

| Requirement | Applies to |
| --- | --- |
| Windows OS | Direct `creon`; gateway process |
| 32-bit Python | Direct `creon`; gateway process |
| CREON Plus installed and logged in | Direct `creon`; gateway process |
| `ALLOW_LIVE_TRADING=true` | Direct `creon`; gateway mode |
| `I_UNDERSTAND_LOSS_RISK=true` | Direct `creon`; gateway mode |
| `CREON_ACCOUNT_NO` configured | Live order placement and account snapshot |

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
