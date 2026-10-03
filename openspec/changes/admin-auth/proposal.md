# Proposal

## Why

The server from `server-api` has open routes, which is safe only while it
listens on `127.0.0.1` and no other site can reach it. To use wosarcher
from a phone or another machine on the LAN, and to stop malicious web pages
from driving a local server through the browser, the owner needs one admin
password, browser sessions, API tokens for scripts, and cross-site request
checks.

## What Changes

- `wosarcher auth set-password [--print]`: prompts for a password and stores
  its scrypt hash (with a new session secret) in `auth.json` in the config
  directory; `--print` prints the hash for `WOSARCHER_AUTH__PASSWORD_HASH`
  instead.
- `wosarcher serve` refuses a non-loopback `--host` unless a password is
  set.
- Browser sessions: `POST /api/login` sets a signed, `HttpOnly`,
  `SameSite=Strict` cookie (`Secure` over HTTPS) valid for
  `auth.session_days` (30); `POST /api/logout`; `GET /api/session`.
  Changing the password ends every session.
- Login rate limit per client IP: 5 failures per minute, then pauses that
  double from 30 seconds; failed logins answer with `attempts_left`,
  paused ones with `retry_after`; failures are logged.
- API tokens `wosarcher_` + 36 random base62 characters, stored as SHA-256
  hashes with name, created, last used, and the last 4 characters:
  `wosarcher auth new-token|list-tokens|revoke-token` and
  `GET/POST/DELETE /api/tokens` (a new token is shown once).
- A request guard for every `/api` route and the event WebSocket: a valid
  session or token is required (except `POST /api/login`); `Origin` must
  match the server's own origin on state-changing requests and WebSocket
  handshakes; state-changing bodies must be JSON (multipart only for
  `POST /api/runs`); with no password set, the `Host` header must name a
  loopback host.

## Non-goals

- More than one user, roles, sign-up, or password reset by mail.
- Changing the password from the browser. It is a CLI action on the
  server machine.
- TLS termination. Use Tailscale or a local reverse proxy (design:
  Transport).
- Persisting the login rate limiter or revoking a single browser session.
  Logout clears the cookie; ending all sessions means changing the
  password.
- New cryptography dependencies: `hashlib`, `hmac`, and `secrets` only.

## Capabilities

### New Capabilities

- `admin-auth`: password storage, bind refusal, browser sessions, login
  rate limiting, API tokens, and the request guard (authentication, Origin,
  content type, Host) for the HTTP API and the event WebSocket.

### Modified Capabilities

None. `http-api` routes keep their behaviour for authenticated requests;
the new requirements are additive and live in `admin-auth`.

## Impact

- New code: `src/wosarcher/auth.py` (stdlib only: password hashing, tokens,
  session signing, `auth.json` store), `server/guard.py` (ASGI middleware),
  `server/login.py` (login, logout, session, rate limiter),
  `server/tokens.py` (token routes), `auth` commands in `cli/auth.py`, tests in
  `tests/auth/`.
- Changed code: `config.py` gains `AuthConfig(password_hash, session_days,
  allowed_origins)` as `Settings.auth`; `models.py` gains the login,
  session, and token response models (included in `wosarcher schema`);
  `cli/serve.py` `serve` checks the bind
  address; `server/__init__.py` installs the guard and routes; the
  server-api test client uses the base URL `http://127.0.0.1:8765` so the
  loopback `Host` check passes.
- `scripts/check_architecture.py`: add `"auth": {"config"}` and add `auth`
  to the `server` and `cli` entries. Reason: password and token handling is
  shared by the CLI and the server and must not pull FastAPI into the CLI's
  `auth` commands.
- No new dependencies.
- docs/design.md sections implemented: Authentication, Server (`/session`,
  `/tokens`).
- docs/design.md changes: routes are under `/api` (`POST /api/login`);
  with no password set, the server binds loopback only and treats requests
  as authenticated, with Origin and loopback `Host` checks still applied;
  token management needs a browser session; the rate limit pause is 30
  seconds, doubling up to 15 minutes.
