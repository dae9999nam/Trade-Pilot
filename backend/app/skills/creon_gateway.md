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

## CREON mapping

| Logical field | CREON value |
| --- | --- |
| `BUY` | `CpTd0311` input value 0 = `2` |
| `SELL` | `CpTd0311` input value 0 = `1` |
| `MARKET` | order type code `03` |
| `LIMIT` | order type code `01` |

## Safety notes

- The gateway is the live-trading boundary, not Docker.
- Do not call live order endpoints unless the user intent and environment gates
  are explicit.
- If CREON login, trade password, account number, or COM initialization fails,
  the gateway returns HTTP 503 with the runtime error message.
