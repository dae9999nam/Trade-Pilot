# Skill: Order Management

## Purpose

Use this skill when the user asks to stage a manual order, approve a pending
order, list orders, or understand order status.

## Endpoints

### `POST /api/orders`

Stages a manual order with status `PENDING_APPROVAL`.

Request body: `OrderCreate`

| Field | Type | Required | Validation | Meaning |
| --- | --- | --- | --- | --- |
| `symbol` | string | yes | length 2 to 16 | Stock symbol. Converted to uppercase. |
| `side` | `BUY` / `SELL` | yes | enum | Order direction. |
| `quantity` | integer | yes | `> 0` | Number of shares. |
| `order_type` | `MARKET` / `LIMIT` | no | enum, default `LIMIT` | Order type. |
| `limit_price` | decimal or null | no | `>= 0` | Price for limit orders. |

Response body: `OrderView`

### `POST /api/orders/{order_id}/approve`

Submits a pending or previously rejected order to the active broker.

Path variables:

| Variable | Type | Required | Meaning |
| --- | --- | --- | --- |
| `order_id` | integer | yes | Existing order ID. |

Behavior:

| Existing status | Behavior |
| --- | --- |
| `PENDING_APPROVAL` | Submit to active broker. |
| `REJECTED` | Retry submission to active broker. |
| Any other status | Return the order unchanged. |

### `GET /api/orders`

Lists up to 50 most recent orders, newest first.

## Order fields

`OrderView`

| Field | Type | Meaning |
| --- | --- | --- |
| `id` | integer | Order ID. |
| `mode` | string | Broker mode used when the order was created. |
| `symbol` | string | Stock symbol. |
| `side` | `BUY` / `SELL` | Order side. |
| `quantity` | integer | Number of shares. |
| `order_type` | `MARKET` / `LIMIT` | Order type. |
| `limit_price` | decimal or null | Limit price if supplied. |
| `status` | string | `PENDING_APPROVAL`, `FILLED`, `SUBMITTED`, `REJECTED`, or broker-returned status. |
| `broker_order_id` | string or null | External broker order ID if available. |
| `message` | string or null | Broker or system message. |

## Broker submission behavior

| Broker mode | Approval result |
| --- | --- |
| `paper` | `PaperBroker.place_order` returns `FILLED`; paper position is updated. |
| `creon` | Direct CREON COM order is submitted. Requires Windows 32-bit Python and live-trading gates. |
| `creon_gateway` | Backend sends the order to the Windows gateway `/orders` endpoint. |

## Safety notes

- Do not infer missing order fields. Ask the user for symbol, side, quantity, and
  limit price when needed.
- Manual order staging does not run `RiskManager` in the current implementation.
- Approval is the action that sends an order to the broker.
- Market orders use `limit_price=null`; paper position update currently falls
  back to price `1` when no limit price is available.
