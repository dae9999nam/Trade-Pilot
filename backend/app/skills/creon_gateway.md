# Skill: CREON Gateway

## Purpose

Use this skill for the Windows-native gateway that owns CREON Plus COM calls.
The main backend uses this service when `BROKER_MODE=creon_gateway`.

## Runtime requirements

| Requirement | Value |
| --- | --- |
| OS | Windows |
| Python | 32-bit Python process |
| Package | `pywin32` installed |
| CREON Plus | Installed, logged in, trade password configured |
| Environment gates | `ALLOW_LIVE_TRADING=true` and `I_UNDERSTAND_LOSS_RISK=true` |
| Account | `CREON_ACCOUNT_NO` configured for orders |
| Gateway token | `GATEWAY_TOKEN` configured when live trading is enabled |

## Docker modes

| Mode | Command | Notes |
| --- | --- | --- |
| Recommended gateway process | `uvicorn main:app --host 0.0.0.0 --port 8765` on Windows | Uses the Windows user's installed and logged-in CREON Plus session. |
| Windows helper setup | `.\infra\windows\setup-creon-gateway.ps1` | Prepares 32-bit Python gateway runtime inside an existing Windows host/VM; does not create the VM or automate broker login. |
| Main app with live gateway | `docker compose -f docker-compose.yml -f docker-compose.creon-gateway.yml up --build -d` | Backend remains containerized and calls the external Windows gateway. |
| Experimental Windows container gateway | `docker compose -f docker-compose.windows.yml up --build -d creon-gateway` | Requires Windows containers. Does not automatically inherit host COM/login state. |

## Authentication

If `GATEWAY_TOKEN` is configured, requests to quote and order endpoints must
include:

| Header | Value |
| --- | --- |
| `x-trade-pilot-token` | Gateway token |

## Gateway endpoints

### `GET /health`

Read-only health check.

Response fields:

| Field | Type | Meaning |
| --- | --- | --- |
| `status` | string | Expected `ok`. |
| `live_trading_enabled` | boolean | Gateway-side live-trading gate state. |
| `runtime` | object | Platform, Python bitness, pywin32, token/account config, and optional CREON connection fields. |

### `GET /ready`

Readiness check for live gateway use. Returns `200` with `status=ready` only
when Windows, 32-bit Python, pywin32, live gates, account config, gateway token,
and CREON connection are all available. Returns `503` with `status=not_ready`
and a `runtime.message` explaining missing prerequisites otherwise.

### `GET /quote/{symbol}`

Returns CREON quote data for an uppercase symbol.

Path variables:

| Variable | Type | Required | Meaning |
| --- | --- | --- | --- |
| `symbol` | string | yes | Stock symbol. |

Response body: `QuoteResponse`

| Field | Type | Meaning |
| --- | --- | --- |
| `symbol` | string | Symbol. |
| `price` | decimal | Last price from CREON. |
| `open_price` | decimal or null | Opening price. |
| `high_price` | decimal or null | High price. |
| `low_price` | decimal or null | Low price. |
| `volume` | integer or null | Volume. |
| `source` | string | Expected `creon`. |
| `as_of` | datetime or null | Gateway timestamp for the response. |

### `POST /orders`

Submits a CREON order.

Request body: `OrderRequest`

| Field | Type | Required | Validation | Meaning |
| --- | --- | --- | --- | --- |
| `symbol` | string | yes | length 2 to 16 | Stock symbol. |
| `side` | `BUY` / `SELL` | yes | enum | Direction. |
| `quantity` | integer | yes | `> 0` | Number of shares. |
| `order_type` | `MARKET` / `LIMIT` | yes | enum | CREON order type mapping. |
| `limit_price` | decimal or null | no | `>= 0` | Price for limit orders. |

Response body: `OrderResponse`

| Field | Type | Meaning |
| --- | --- | --- |
| `broker_order_id` | string or null | CREON order number when available. |
| `status` | `SUBMITTED` / `REJECTED` | Gateway status mapping. |
| `message` | string | CREON status message. |
| `creon_status_code` | integer or null | CREON DIB status code from the order request. |
| `submitted_at` | datetime or null | Gateway timestamp for the order response. |

### `GET /account`

Returns a CREON account holdings snapshot through `CpTrade.CpTd6033`.

Response body: `AccountSnapshotResponse`

| Field | Type | Meaning |
| --- | --- | --- |
| `source` | string | Expected `creon`. |
| `cash_krw` | decimal or null | Currently null; cash balance mapping is separate from `CpTd6033`. |
| `positions` | array | Current non-zero CREON holding rows. |
| `as_of` | datetime or null | Gateway observation timestamp. |
| `raw_payload` | object or null | CREON object, goods code, page count, and position count. |

Position fields:

| Field | Type | Meaning |
| --- | --- | --- |
| `symbol` | string | Normalized stock symbol. Numeric six-digit CREON codes are returned as `A######`. |
| `quantity` | integer | Holding quantity. |
| `name` | string or null | CREON security name. |
| `avg_price` | decimal or null | Average book price when provided. |
| `market_price` | decimal or null | Current price. Signed CREON price values are normalized to absolute values. |
| `available_quantity` | integer or null | Quantity available for sell/order actions when provided. |
| `market_value` | decimal or null | CREON market value field when provided. |
| `raw_payload` | object or null | Field index diagnostics. |

### `GET /orders/{broker_order_id}`

Order status refresh endpoint scaffold. The route exists so the backend can use
one broker lifecycle interface, but the current gateway returns
`creon_order_status_not_implemented` until the CREON COM status lookup is
implemented.

Response body shape: `OrderStatusResponse`

| Field | Type | Meaning |
| --- | --- | --- |
| `broker_order_id` | string or null | CREON order number. |
| `status` | string | Normalized broker status when implemented. |
| `message` | string | Gateway message. |
| `filled_quantity` | integer or null | Filled quantity when implemented. |
| `remaining_quantity` | integer or null | Remaining quantity when implemented. |
| `creon_status_code` | integer or null | CREON status code when available. |
| `as_of` | datetime or null | Gateway observation timestamp. |
| `raw_payload` | object or null | CREON-specific diagnostic payload. |

### `POST /orders/{broker_order_id}/cancel`

Order cancellation endpoint scaffold. The route exists but currently returns
`creon_order_cancel_not_implemented`. Until CREON COM cancel mapping is
implemented and tested, live orders must be canceled directly in CREON Plus.

## Error payload

Gateway runtime errors return HTTP 503 with structured detail:

| Field | Meaning |
| --- | --- |
| `detail.code` | Stable error category such as `creon_com_busy`, `creon_unavailable`, or `creon_quote_rejected`. |
| `detail.message` | Human-readable reason. |
| `detail.retryable` | Whether a retry may make sense. Orders are not retried automatically. |
| `detail.request_id` | Gateway request ID also emitted as `x-request-id`. |

## Stability behavior

| Behavior | Reason |
| --- | --- |
| Process-wide COM lock | CREON COM calls are serialized to avoid concurrent access to the HTS COM session. |
| Quote retry only | Quotes are read-only and can retry bounded transient failures. |
| No automatic order retry | Prevents duplicate live orders when a broker response is ambiguous. |
| Status/cancel scaffold is explicit | Backend can record lifecycle events without pretending unsupported CREON COM operations succeeded. |
| Constant-time token comparison | Reduces token comparison timing leakage. |
| `/ready` separated from `/health` | Liveness remains cheap; readiness can touch CREON COM. |

## CREON mapping

| Logical field | CREON value |
| --- | --- |
| `BUY` | `CpTd0311` input value 0 = `2` |
| `SELL` | `CpTd0311` input value 0 = `1` |
| `MARKET` | order type code `03` |
| `LIMIT` | order type code `01` |
| Account snapshot | `CpTd6033` input value 0 = account number |
| Account goods code | `CpTd6033` input value 1 = `CREON_GOODS_CODE` |
| Account request count | `CpTd6033` input value 2 = `50` |
| Account row count | `CpTd6033` header value 7 |
| Account symbol | `CpTd6033` data value 12 |
| Account quantity | `CpTd6033` data value 7 |
| Account current price | `CpTd6033` data value 9 |
| Account market value | `CpTd6033` data value 11 |
| Account available quantity | `CpTd6033` data value 15 |
| Account average price | `CpTd6033` data value 17 |

## Safety notes

- The gateway is the live-trading boundary, not Docker.
- Do not call live order endpoints unless the user intent and environment gates
  are explicit.
- If CREON login, trade password, account number, or COM initialization fails,
  the gateway returns HTTP 503 with the runtime error message.
