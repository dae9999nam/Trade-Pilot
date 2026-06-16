# Skill: User and Admin Authentication

## Purpose

Use this skill when a web app needs to register a user, sign in, validate the
current identity, sign out, or call authenticated endpoints.

## Endpoints

### `POST /api/auth/register`

Creates a regular `user` account when registration is enabled.

Request body: `RegisterRequest`

| Field | Type | Required | Validation |
| --- | --- | --- | --- |
| `email` | string | yes | length 3 to 320; normalized to lowercase |
| `password` | string | yes | length 12 to 256 |

Response body: `LoginResponse`. The response also sets the session and CSRF
cookies.

### `POST /api/auth/login`

Request body: `LoginRequest`

| Field | Type | Required | Validation |
| --- | --- | --- | --- |
| `username` | string | yes | length 1 to 320; normalized to lowercase |
| `password` | string | yes | length 1 to 256 |

Response body: `LoginResponse`

| Field | Type | Meaning |
| --- | --- | --- |
| `csrf_token` | string | CSRF token also stored in the readable CSRF cookie. |
| `token_type` | `cookie` | Authentication is an HttpOnly cookie session. |
| `user` | `UserProfile` | Authenticated user profile. |

The backend stores only hashes of session and CSRF tokens in `user_sessions`.
The plaintext session token is only sent as an HttpOnly cookie.

### `GET /api/auth/me`

Requires a valid session cookie. Returns `UserProfile`.

### `POST /api/auth/logout`

Requires a valid session cookie and matching CSRF token. Revokes the current
server-side session and clears auth cookies.

## Authenticated request behavior

| Request part | Requirement |
| --- | --- |
| `Cookie: trade_pilot_session=...` | Required for every authenticated endpoint. Browser clients send this with `credentials: "include"`. |
| `Cookie: trade_pilot_csrf=...` | Required for unsafe authenticated methods. |
| `X-CSRF-Token` | Must match the CSRF cookie and the stored CSRF token hash on `POST`, `PUT`, `PATCH`, and `DELETE`. |

Returns `UserProfile`:

| Field | Type | Meaning |
| --- | --- | --- |
| `id` | integer | Stable database user id. |
| `username` | string | Same value as `email` for compatibility. |
| `email` | string | Normalized login email or bootstrap admin username. |
| `role` | `user` or `admin` | Current role. |

## Session behavior

| Setting | Meaning |
| --- | --- |
| `ADMIN_USERNAME` | Bootstrap admin username. |
| `ADMIN_PASSWORD` | Bootstrap admin password. Must be changed outside local development. |
| `SESSION_TTL_MINUTES` | Server-side session and cookie expiry window. |
| `SESSION_COOKIE_NAME` | HttpOnly session cookie name. |
| `CSRF_COOKIE_NAME` | Readable CSRF cookie name. |
| `AUTH_COOKIE_SECURE` | Set to `true` behind HTTPS in production. |
| `AUTH_COOKIE_SAMESITE` | `lax`, `strict`, or `none`. Use `none` only with secure cross-site cookies. |
| `ALLOW_USER_REGISTRATION` | Enables or disables public user registration. |

## Safety notes

- Never print or persist plaintext passwords in model output.
- Do not ask for credentials unless the user is explicitly trying to log in,
  register, or configure authentication.
- Do not invent bearer tokens, JWTs, or custom auth headers. This system uses
  server-side cookie sessions.
- Admin-only endpoints require `role = admin`; regular users must stay scoped
  to their own portfolio, orders, positions, and decisions.
