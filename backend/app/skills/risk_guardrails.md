# Skill: Risk Guardrails

## Purpose

Use this skill when explaining why a trade decision was approved, rejected, or
requires approval. Also use it before proposing executable order behavior.

## Backend service

`RiskManager.evaluate(decision, snapshot, max_position_krw=None) -> RiskResult`

## Input variables

| Variable | Source | Meaning |
| --- | --- | --- |
| `decision.action` | `TradeDecisionPayload` | `BUY`, `SELL`, or `HOLD`. |
| `decision.quantity` | `TradeDecisionPayload` | Proposed quantity. |
| `decision.limit_price` | `TradeDecisionPayload` | Used for notional when present. |
| `decision.confidence` | `TradeDecisionPayload` | Compared with `MIN_DECISION_CONFIDENCE`. |
| `decision.require_human_approval` | `TradeDecisionPayload` | Can force `NEEDS_APPROVAL` or rejection depending on other reasons. |
| `snapshot.price` | `MarketSnapshot` | Used for notional when no limit price is present. |
| `max_position_krw` | request or settings | Per-request override or default position cap. |

## Checks

| Check | Rejection or approval effect |
| --- | --- |
| `action == HOLD` | Immediately returns `APPROVED` with notional `0`. |
| `quantity <= 0` for executable action | Adds rejection reason. |
| `confidence < min_decision_confidence` | Adds rejection reason. |
| `quantity * price > max_order_krw` | Adds rejection reason. |
| `quantity * price > max_position_krw` | Adds rejection reason. |
| `require_human_approval == true` | Adds approval requirement reason. |
| `broker_mode == creon` and live trading disabled | Adds rejection reason. |

## Output variables

`RiskResult`

| Field | Type | Meaning |
| --- | --- | --- |
| `status` | `APPROVED` / `REJECTED` / `NEEDS_APPROVAL` | Deterministic risk outcome. |
| `reasons` | array of strings | Human-readable guardrail results. |
| `notional_krw` | decimal | Quantity multiplied by limit price or snapshot price. |

## Safety notes

- `RiskManager` is the deterministic boundary between AI output and executable
  order creation.
- Manual orders currently bypass `RiskManager` when staged, but still require
  explicit approval before broker submission.
- The current implementation checks direct `creon` live-trading state in
  `RiskManager`; `creon_gateway` live-trading state is enforced when the broker
  adapter is constructed.
