# Skill: System Status and Public Configuration

## Purpose

Use this skill when the user asks whether the system is running, which broker is
active, whether auto-execution or live trading is enabled, which OpenAI model is
configured, or what deterministic trading limits are active.

## When to use

- User asks "is the backend alive", "what mode are we in", "paper or live",
  "what are the limits", "which model is being used", or similar.
- A trading decision needs current risk configuration before reasoning.
- A UI needs public configuration values.

## Backend endpoints

### `GET /api/health`

Read-only health check.

Response fields:

| Field | Type | Meaning |
| --- | --- | --- |
| `status` | string | Expected value is `ok` when FastAPI is running. |
| `broker_mode` | string | Active broker mode from settings. |

### `GET /api/config`

Read-only public configuration.

Response fields:

| Field | Type | Meaning |
| --- | --- | --- |
| `app_env` | string | Application environment name. |
| `broker_mode` | `paper` / `creon` / `creon_gateway` | Active broker implementation. |
| `auto_execute` | boolean | Whether approved AI decisions become submitted orders automatically. |
| `live_trading_enabled` | boolean | True only when live-trading gates are enabled. |
| `openai_model` | string | Model name used by `AgentOrchestrator`. |
| `max_order_krw` | integer | Maximum order notional allowed by deterministic risk checks. |
| `max_position_krw` | integer | Default maximum position notional. |
| `min_decision_confidence` | number | Minimum confidence required for executable decisions. |

## Required variables

None.

## Safety notes

- These endpoints do not execute trades.
- Use `live_trading_enabled`, not just `broker_mode`, to decide whether live
  order execution is allowed.
- `broker_mode=creon_gateway` still requires the Windows gateway to be running
  and reachable.
