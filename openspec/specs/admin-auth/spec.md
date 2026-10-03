# admin-auth Specification

## Purpose

Keeps everyone but the owner out of a wosarcher server that other devices
can reach, with one admin password, browser sessions, API tokens for
scripts, and checks against cross-site requests and DNS rebinding.

## Requirements

### Requirement: Password storage
`wosarcher auth set-password` SHALL prompt twice for a password of at least
8 characters and store only its scrypt hash, with its salt and parameters,
in `auth.json` in the wosarcher config directory, readable only by the
owner (mode 0600). The plain password SHALL never be stored or logged.
With `--print` it SHALL print the hash instead of storing it. When
`WOSARCHER_AUTH__PASSWORD_HASH` is set, it SHALL be used instead of the
stored hash, and `set-password` without `--print` SHALL warn that the
environment variable takes precedence.

#### Scenario: Set a password
- **WHEN** the user runs `wosarcher auth set-password` and enters the same password twice
- **THEN** `auth.json` contains a hash starting with `scrypt$`, does not contain the password, and has mode 0600

#### Scenario: Mismatched confirmation
- **WHEN** the two entered passwords differ
- **THEN** nothing is stored and the command exits with a non-zero code

#### Scenario: Hash from the environment
- **WHEN** `WOSARCHER_AUTH__PASSWORD_HASH` holds the hash of `hunter22` and `auth.json` holds a different hash
- **THEN** logging in with `hunter22` succeeds

### Requirement: Authentication mode
Authentication SHALL be enabled when a password hash is configured. When it
is not, every request SHALL be treated as authenticated, and the other
checks in this capability (Origin, content type, loopback Host) SHALL still
apply. A password set while the server runs SHALL take effect without a
restart.

#### Scenario: Password set while running
- **WHEN** the server runs without a password and the owner runs `wosarcher auth set-password`
- **THEN** the next `GET /api/runs` without a session or token answers 401

### Requirement: Loopback bind without a password
`wosarcher serve` SHALL refuse to start, with a message naming
`wosarcher auth set-password` and a non-zero exit code, when the host is not
a loopback address (`127.0.0.0/8`, `::1`, or `localhost`) and no password
hash is configured.

#### Scenario: LAN bind without password
- **WHEN** no password is set and the user runs `wosarcher serve --host 0.0.0.0`
- **THEN** the server does not start and the command exits non-zero

#### Scenario: LAN bind with password
- **WHEN** a password is set and the user runs `wosarcher serve --host 0.0.0.0`
- **THEN** the server starts

### Requirement: Protected routes
Every route under `/api`, including the event WebSocket, SHALL require a
valid session cookie or API token, except `POST /api/login`. Unauthenticated
requests SHALL answer 401 with `error = "unauthenticated"`; an
unauthenticated WebSocket handshake SHALL be rejected. Static frontend
files (including the `/login` page) SHALL be served without
authentication.

#### Scenario: No credentials
- **WHEN** a password is set and a client sends `GET /api/runs` with no cookie and no token
- **THEN** the response is 401

#### Scenario: Static page
- **WHEN** a password is set and a browser requests `/login`
- **THEN** the frontend's `index.html` is served

### Requirement: Login
`POST /api/login` with JSON `{"password": ...}` SHALL, for the right
password, set a session cookie and answer 200 with the session. For a wrong
password it SHALL answer 401 with `error = "wrong_password"` and
`attempts_left`, the failures the client IP may still make before a pause.
When no password is configured it SHALL answer 409 with
`error = "auth_disabled"`.

#### Scenario: Right password
- **WHEN** a client logs in with the right password
- **THEN** the response is 200 and sets the `wosarcher_session` cookie

#### Scenario: Wrong password
- **WHEN** a client with no earlier failures logs in with a wrong password
- **THEN** the response is 401 with `attempts_left = 4`

### Requirement: Login rate limit
Failed logins SHALL be counted per client IP. The fifth failure within 60
seconds SHALL pause logins from that IP for 30 seconds; each further pause
SHALL double, up to 15 minutes. While paused, every login attempt,
including one with the right password, SHALL answer 429 with
`error = "rate_limited"`, `retry_after` in whole seconds, and a matching
`Retry-After` header. A successful login, or 15 minutes without a failure,
SHALL reset the count and the pause length. Each failure SHALL be logged
with the client IP and never the submitted password.

#### Scenario: Fifth failure
- **WHEN** a client IP fails to log in five times within one minute
- **THEN** the fifth response is 429 with `retry_after = 30`

#### Scenario: Right password while paused
- **WHEN** a paused client IP sends the right password
- **THEN** the response is 429 and no cookie is set

#### Scenario: Backoff doubles
- **WHEN** a client IP fails five more times after its first pause ends
- **THEN** the next pause is 60 seconds

#### Scenario: Other IPs unaffected
- **WHEN** one client IP is paused
- **THEN** a login from another IP with the right password succeeds

### Requirement: Session cookie
The session cookie SHALL be named `wosarcher_session` and hold a random
token, its issue and expiry times, and an HMAC-SHA256 signature. It SHALL
be `HttpOnly`, `SameSite=Strict`, `Path=/`, `Secure` when the request
arrived over HTTPS, and expire after `auth.session_days` days (default 30).
A cookie with a bad signature or past its expiry SHALL be rejected. A
malformed cookie value, including one with non-ASCII characters, SHALL be
rejected the same way (401), never answered with a server error.

#### Scenario: Cookie attributes over HTTPS
- **WHEN** a client logs in through a request whose scheme is `https`
- **THEN** the cookie has `HttpOnly`, `SameSite=Strict`, `Secure`, and a max age of 30 days

#### Scenario: Tampered cookie
- **WHEN** a client changes the expiry inside its cookie
- **THEN** its next request answers 401

#### Scenario: Non-ASCII cookie
- **WHEN** a request carries `wosarcher_session=é.1.2.sig` while a password is set
- **THEN** the response is 401 `unauthenticated`

### Requirement: Logout and session info
`POST /api/logout` SHALL clear the session cookie and answer 204.
`GET /api/session` SHALL return how the request is authenticated (`cookie`,
`token`, or `none` when authentication is disabled), and for a cookie its
`since` and `expires` times, for a token its name.

#### Scenario: Session details
- **WHEN** a browser that logged in at 09:12 requests `GET /api/session`
- **THEN** the response has `method = "cookie"` and `since` at 09:12

### Requirement: Password change ends sessions
Changing the password SHALL invalidate every existing session cookie. API
tokens SHALL stay valid.

#### Scenario: Old cookie after a change
- **WHEN** the owner sets a new password while a browser holds a session cookie
- **THEN** that browser's next request answers 401

### Requirement: API tokens
API tokens SHALL be `wosarcher_` followed by 36 random base62 characters and
SHALL be stored only as SHA-256 hashes, with an ID, a name, the creation
time, the last-used time, and the last 4 characters. A request with
`Authorization: Bearer <token>` for a stored token SHALL be authenticated
and SHALL update the token's last-used time (at most once per minute). The
CLI SHALL provide `wosarcher auth new-token <name>` (prints the token
once), `wosarcher auth list-tokens`, and `wosarcher auth revoke-token <id>`.
The API SHALL provide `GET /api/tokens` (never the token or its hash),
`POST /api/tokens` with `{"name"}` (answers 201 with the token, once), and
`DELETE /api/tokens/{id}` (204, or 404 for an unknown ID). Token routes
SHALL require a browser session (or disabled authentication); a request
authenticated by a token SHALL get 403 on them.

#### Scenario: Script with a token
- **WHEN** a script sends `GET /api/runs` with a valid bearer token
- **THEN** the response is 200 and the token's last-used time is set

#### Scenario: Revoked token
- **WHEN** a token is revoked with `wosarcher auth revoke-token <id>` while the server runs
- **THEN** the next request with that token answers 401

#### Scenario: Token shown once
- **WHEN** a browser creates a token and then lists tokens
- **THEN** the create response contains the token and the list shows only its name, dates, and masked last 4 characters

#### Scenario: Token cannot mint tokens
- **WHEN** a request authenticated by a bearer token sends `POST /api/tokens`
- **THEN** the response is 403

### Requirement: Origin check
For `POST`, `PUT`, `PATCH`, and `DELETE` requests and for WebSocket
handshakes that carry an `Origin` header, the origin SHALL equal the
server's own origin (the request scheme and `Host` header) or one of
`auth.allowed_origins`; otherwise the request SHALL answer 403 with
`error = "bad_origin"`, or the handshake SHALL be rejected. A request
without an `Origin` header (a non-browser client) SHALL pass this check.

#### Scenario: Cross-site POST
- **WHEN** a request to `POST /api/runs` carries `Origin: https://evil.example` and a valid session cookie
- **THEN** the response is 403 and no run is created

#### Scenario: Cross-site WebSocket
- **WHEN** a WebSocket handshake to `/api/runs/{id}/events` carries a valid cookie and a foreign `Origin`
- **THEN** the handshake is rejected

#### Scenario: Same origin
- **WHEN** a browser at `http://127.0.0.1:8765` sends `POST /api/runs/{id}/cancel` with `Origin: http://127.0.0.1:8765` and a valid cookie
- **THEN** the Origin check passes

### Requirement: JSON-only bodies
`POST`, `PUT`, `PATCH`, and `DELETE` requests with a body SHALL have
`Content-Type: application/json`, except `POST /api/runs`, which SHALL be
`multipart/form-data`. Other content types SHALL answer 415 with
`error = "unsupported_media_type"`.

#### Scenario: Form post
- **WHEN** a request to `PUT /api/settings` has `Content-Type: application/x-www-form-urlencoded`
- **THEN** the response is 415 and the settings are unchanged

### Requirement: Loopback Host without a password
When no password is configured, requests whose `Host` header names
anything other than `localhost`, `127.0.0.1`, or `[::1]` (with any port)
SHALL answer 403 with `error = "bad_host"`, so a DNS-rebound page cannot
reach the open API.

#### Scenario: Rebound host name
- **WHEN** no password is set and a request arrives with `Host: attacker.example:8765`
- **THEN** the response is 403

### Requirement: Trusted proxies
The server SHALL take the client address and the request scheme from
`X-Forwarded-For` and `X-Forwarded-Proto` only when the direct peer's
address is in `server.forwarded_allow_ips` (a list of IP addresses or
networks, or `"*"`; default `["127.0.0.1"]`). The scheme taken this way
SHALL be used by the Origin check and the cookie's `Secure` attribute, and
the client address by the login rate limit.

#### Scenario: TLS proxy on the Docker bridge
- **WHEN** `server.forwarded_allow_ips = ["172.17.0.1"]` and a proxy at 172.17.0.1 forwards a browser's `POST /api/runs` with `X-Forwarded-Proto: https`, `Host: wos.lan`, and `Origin: https://wos.lan`
- **THEN** the Origin check passes

#### Scenario: Untrusted peer
- **WHEN** a client at 192.168.1.20, not in `server.forwarded_allow_ips`, sends `X-Forwarded-For: 10.0.0.9`
- **THEN** the login rate limit counts its failures under 192.168.1.20
