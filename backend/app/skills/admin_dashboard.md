# Skill: Admin Dashboard

## Purpose

Use this skill for admin-only account summary, transaction history, recent AI
decisions, and dashboard-level operational status.

## Authentication

These endpoints require an authenticated session for a user whose role is
`admin`.

Browser clients must send cookies with `credentials: "include"`. Unsafe
requests must also send the readable CSRF cookie value in `X-CSRF-Token`.

| Request part | Value |
| --- | --- |
| Session cookie | `trade_pilot_session` or configured `SESSION_COOKIE_NAME` |
| CSRF header | `X-CSRF-Token: <trade_pilot_csrf>` for unsafe methods |

## Endpoints

### `GET /api/dashboard/summary`

Returns current user, broker mode, live-trading state, portfolio totals, order
counts, recent transactions, positions, and recent decisions.

Key response fields:

| Field | Type | Meaning |
| --- | --- | --- |
| `user` | `UserProfile` | Authenticated admin user. |
| `broker_mode` | string | Active broker mode. |
| `live_trading_enabled` | boolean | Live-trading gate state. |
| `auto_execute` | boolean | Auto-execution state. |
| `total_market_value` | decimal | Sum of quantity times market price. |
| `total_cost_basis` | decimal | Sum of quantity times average price. |
| `unrealized_pnl` | decimal | Market value minus cost basis. |
| `positions_count` | integer | Count of non-zero positions. |
| `open_orders_count` | integer | Count of non-terminal recent orders: `PENDING_APPROVAL`, `APPROVED`, `SUBMITTING`, `SUBMITTED`, `PARTIALLY_FILLED`, and `SUBMISSION_FAILED`. |
| `filled_orders_count` | integer | Count of recent filled orders. |
| `rejected_orders_count` | integer | Count of recent rejected orders. |
| `recent_transactions` | array | Recent order transaction views with lifecycle timestamps, `submission_attempts`, `can_approve`, and `is_terminal`. |
| `positions` | array | Current positions. |
| `recent_decisions` | array | Recent AI decision summaries. |

### `GET /api/dashboard/transactions`

Returns up to 100 recent order transaction views, newest first.

## Safety notes

- Use this skill only when admin context is available. A regular `user` role
  must receive a `403` rather than dashboard data.
- Do not request, expose, or store admin passwords in model output.
- These endpoints are read-only.
