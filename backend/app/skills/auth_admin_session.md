# Skill: Admin Authentication

## Purpose

Use this skill when the admin web app needs to sign in, validate the current
admin identity, or call authenticated dashboard endpoints.

## Endpoints

### `POST /api/auth/login`

Request body: `LoginRequest`

| Field | Type | Required | Validation |
| --- | --- | --- | --- |
| `username` | string | yes | length 1 to 64 |
| `password` | string | yes | length 1 to 256 |

Response body: `LoginResponse`

| Field | Type | Meaning |
| --- | --- | --- |
| `access_token` | string | HMAC-signed bearer token. |
| `token_type` | `bearer` | Token type. |
| `user` | `UserProfile` | Authenticated admin profile. |

### `GET /api/auth/me`

Requires `Authorization: Bearer <access_token>`.

Returns `UserProfile`:

| Field | Type | Meaning |
| --- | --- | --- |
| `username` | string | Admin username. |
| `role` | `admin` | Current role. |

## Token behavior

| Setting | Meaning |
| --- | --- |
| `ADMIN_USERNAME` | Expected username. |
| `ADMIN_PASSWORD` | Expected password. |
| `ADMIN_TOKEN_SECRET` | HMAC signing secret. |
| `ACCESS_TOKEN_TTL_MINUTES` | Token expiry window. |

## Safety notes

- Never print or persist plaintext passwords in model output.
- Do not ask for admin credentials unless the user is explicitly trying to log
  in or configure the admin dashboard.
- Use the bearer token only for authenticated admin endpoints.
