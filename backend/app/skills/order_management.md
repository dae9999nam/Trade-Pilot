# Skill: Order Management

## Purpose

Use this skill when the user asks to stage a manual order, approve or retry an
approvable order, list orders, inspect order events, or understand order
lifecycle status.

## Endpoints

### `POST /api/orders`

Stages a manual order with status `PENDING_APPROVAL` and writes an
`order_events` row with event type `manual_order_staged`.

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

Submits an approvable order to the active broker.

Path variables:

| Variable | Type | Required | Meaning |
| --- | --- | --- | --- |
| `order_id` | integer | yes | Existing order ID. |

Behavior:

| Existing status | Behavior |
| --- | --- |
| `PENDING_APPROVAL` | Mark `APPROVED`, then `SUBMITTING`, then submit to active broker. |
| `SUBMISSION_FAILED` | Retry submission with a new `submission_attempts` increment. |
| Any other status | Return the order unchanged. |

Approval writes `order_events` for approval, broker submission start, and broker
result or failure.

### `GET /api/orders`

Lists up to 50 most recent orders, newest first.

### `GET /api/orders/{order_id}/events`

Lists the status transition history for a single order, oldest first.

Path variables:

| Variable | Type | Required | Meaning |
| --- | --- | --- | --- |
| `order_id` | integer | yes | Existing order ID owned by the authenticated user. |

Response body: array of `OrderEventView`

| Field | Type | Meaning |
| --- | --- | --- |
| `id` | integer | Event ID. |
| `order_id` | integer | Parent order ID. |
| `from_status` | string or null | Previous status. Null for the initial event. |
| `to_status` | string | New status after the event. |
| `event_type` | string | System event name. |
| `message` | string or null | Broker or system message. |
| `broker_order_id` | string or null | Broker order ID attached to the event, if available. |
| `event_payload` | object or null | Structured details such as broker status or exception type. |
| `created_at` | datetime | Event creation timestamp. |

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
| `status` | string | Current normalized lifecycle status. |
| `broker_order_id` | string or null | External broker order ID if available. |
| `message` | string or null | Broker or system message. |
| `approved_at` | datetime or null | First approval timestamp. |
| `submitted_at` | datetime or null | First broker submission timestamp. |
| `filled_at` | datetime or null | Fill timestamp when status becomes `FILLED`. |
| `rejected_at` | datetime or null | Broker rejection timestamp when status becomes `REJECTED`. |
| `failed_at` | datetime or null | Submission failure timestamp when status becomes `SUBMISSION_FAILED`. |
| `canceled_at` | datetime or null | Cancel timestamp when status becomes `CANCELED`. |
| `last_status_at` | datetime or null | Last lifecycle status change timestamp. |
| `submission_attempts` | integer | Number of broker submission attempts. |
| `can_approve` | boolean | Whether `/approve` can submit or retry this order. |
| `is_terminal` | boolean | Whether the order lifecycle is complete. |
| `created_at` | datetime or null | Order creation timestamp. |
| `updated_at` | datetime or null | Last row update timestamp. |

## Lifecycle statuses

| Status | Meaning | Next common status |
| --- | --- | --- |
| `PENDING_APPROVAL` | Order is staged but not approved. | `APPROVED`, `CANCELED` |
| `APPROVED` | User approved the order for broker submission. | `SUBMITTING`, `CANCELED` |
| `SUBMITTING` | Backend is sending the order to the broker adapter. | `SUBMITTED`, `FILLED`, `REJECTED`, `SUBMISSION_FAILED` |
| `SUBMITTED` | Broker accepted the order but the app has not observed a fill. | `PARTIALLY_FILLED`, `FILLED`, `REJECTED`, `CANCELED` |
| `PARTIALLY_FILLED` | Broker reports a partial fill. | `FILLED`, `REJECTED`, `CANCELED` |
| `FILLED` | Order is fully filled. Terminal. | none |
| `REJECTED` | Broker rejected the order. Terminal. | none |
| `SUBMISSION_FAILED` | Backend/gateway/adapter submission failed before a reliable broker acceptance. | `APPROVED`, `CANCELED` |
| `CANCELED` | Order was canceled. Terminal. | none |

## Broker submission behavior

| Broker mode | Approval result |
| --- | --- |
| `paper` | `PaperBroker.place_order` returns `FILLED`; paper position is updated. |
| `creon` | Direct CREON COM order is submitted. Requires Windows 32-bit Python and live-trading gates. |
| `creon_gateway` | Backend sends the order to the Windows gateway `/orders` endpoint. |

Broker-returned statuses are normalized before storage: `ACCEPTED` maps to
`SUBMITTED`, `EXECUTED` maps to `FILLED`, partial-fill variants map to
`PARTIALLY_FILLED`, reject variants map to `REJECTED`, and unknown statuses map
to `SUBMISSION_FAILED`.

## Safety notes

- Do not infer missing order fields. Ask the user for symbol, side, quantity, and
  limit price when needed.
- Manual order staging does not run `RiskManager` in the current implementation.
- Approval is the action that sends an order to the broker.
- Do not retry a terminal order. Only `can_approve=true` orders are valid
  approve/retry candidates.
- In live modes, inspect `order_events`, gateway request IDs, and broker account
  state before retrying `SUBMISSION_FAILED`; ambiguous network failures can
  create duplicate-order risk.
- Market orders use `limit_price=null`; paper position update currently falls
  back to price `1` when no limit price is available.
