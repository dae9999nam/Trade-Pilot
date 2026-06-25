# Skill: Account Reconciliation

## Purpose

Use this skill when the user asks whether application holdings match the broker
account, whether live CREON positions are synchronized, or why displayed
positions may differ from broker holdings.

## Endpoint

`GET /api/account/reconciliation`

Compares non-zero application positions with the currently configured broker
account snapshot.

## Output variables

Response body: `AccountReconciliationResponse`

| Field | Type | Meaning |
| --- | --- | --- |
| `broker_mode` | string | Active broker mode from backend settings. |
| `broker_source` | string | Broker or snapshot source used for comparison. |
| `broker_status` | `PAPER`, `SYNCED`, or `UNAVAILABLE` | Whether a broker snapshot was available. |
| `message` | string | Human-readable reconciliation status or failure reason. |
| `cash_krw` | decimal or null | Broker-reported KRW cash balance when available. |
| `app_positions` | array | Non-zero positions stored in the application database. |
| `broker_positions` | array | Non-zero positions reported by the broker snapshot. |
| `rows` | array | Symbol-level comparison rows. |
| `as_of` | datetime or null | Snapshot timestamp. |

## Row status values

| Status | Meaning |
| --- | --- |
| `MATCHED` | Application and broker quantities match for the symbol. |
| `MISSING_IN_APP` | Broker reports a position that the application database does not hold. |
| `MISSING_IN_BROKER` | Application database holds a position missing from the broker snapshot. |
| `QUANTITY_MISMATCH` | Both sides have the symbol but quantities differ. |
| `BROKER_UNAVAILABLE` | Broker account snapshot could not be loaded. |

## Broker behavior

| Broker mode | Behavior |
| --- | --- |
| `paper` | Uses the application database as the paper broker ledger and returns `PAPER`. |
| `creon_gateway` | Calls the CREON gateway `/account` endpoint and compares the response. |
| direct `creon` | Uses the broker adapter if it implements account snapshots. |

## Current CREON limitation

The gateway exposes `/account`, but CREON account snapshot COM mapping is not
implemented yet. Until that mapping is added and verified on Windows 32-bit
Python with CREON Plus, live reconciliation returns `UNAVAILABLE` instead of
inventing broker holdings.

## Safety notes

- Do not treat `positions` alone as proof of live account state.
- If `broker_status` is `UNAVAILABLE`, tell the user what capability is missing
  and avoid making claims about actual live holdings.
- Use this skill before answering live account mismatch or live portfolio
  synchronization questions.
