# Design

## Context

`server-api` provides `server/` (app factory, `/api` routes, the event
WebSocket, static files) and `wosarcher serve`; every route is open.
`config.py` resolves `Settings` from defaults, profile, environment, and
overrides, and knows the config directory. See proposal.md for scope and
`specs/admin-auth/spec.md` for behaviour.

## Goals / Non-Goals

**Goals:**

- All authentication decisions in one guard, readable top to bottom.
- Standard library cryptography only, with parameters written down here.
- Password and token changes made by the CLI take effect in a running
  server without a restart.

**Non-Goals:**

- Server-side session storage. Sessions are signed cookies.
- Protecting the static frontend; it holds no data.

## Decisions

### Modules

```
src/wosarcher/auth.py   # stdlib + config: hash_password, verify_password, new_token,
                        # hash_token, sign_session, verify_session, AuthStore
server/guard.py         # Guard: pure ASGI middleware for http and websocket scopes
server/login.py         # LoginLimiter; POST /api/login, POST /api/logout, GET /api/session
server/tokens.py        # GET/POST/DELETE /api/tokens
cli/auth.py             # `auth` sub-app, registered in cli/__init__.py
cli/serve.py            # bind check in `serve` (server-api's command)
```

`auth.py` is a new top-level part so `wosarcher auth ...` does not import
FastAPI. The CLI is the `cli/` package from run-orchestration.

The response bodies are Pydantic models in `models.py`, included in
`wosarcher schema` like server-api's API models, so the frontend's
generated types cover them: `LoginRequest(password)`, `SessionInfo(method:
Literal["cookie", "token", "none"], since: datetime | None, expires:
datetime | None, token_name: str | None)`, `TokenInfo(id, name, masked,
created, last_used)`, `TokenCreate(name)`, `TokenCreated(id, name,
token)`, and `LoginError(error, detail, attempts_left: int | None,
retry_after: int | None)`. `ALLOWED` gains `"auth": {"config"}`, and `auth` is added to
`server` and `cli`.

### Password hashing: `hashlib.scrypt`

Parameters: `n = 2**15`, `r = 8`, `p = 1`, `dklen = 32`, 16-byte salt from
`secrets.token_bytes`, `maxmem = 64 MiB` (n = 2^15 with r = 8 needs 32 MiB,
which is exactly the default limit and fails). Stored format:

```
scrypt$15$8$1$<salt base64url>$<key base64url>
```

`verify_password` reads the parameters from the string, so they can be
raised later without breaking stored hashes, and compares with
`hmac.compare_digest`. A check takes about 50 to 100 ms, so the login
route calls it through `asyncio.to_thread`. Alternative: PBKDF2. Rejected:
scrypt is memory-hard and also in the standard library.

### `auth.json` and `AuthStore`

```json
{"password_hash": "scrypt$...", "secret": "<32 random bytes, base64url>",
 "tokens": [{"id": "a1b2c3d4", "name": "laptop", "sha256": "...",
             "last4": "k9Qz", "created": "...", "last_used": null}]}
```

`AuthStore(path, env_hash)` reloads the file when its `mtime_ns` changes
(one `stat` per request), so CLI changes apply at once. Writes take an
exclusive `fcntl.flock` on `auth.json.lock`, re-read, modify, write a
temporary file with mode 0600, and rename, so the CLI and the server do not
lose each other's updates. The effective password hash is
`Settings.auth.password_hash` (from `WOSARCHER_AUTH__PASSWORD_HASH` or a
profile) when set, else the file's.

`set-password` writes a new hash and a new `secret`.

### Session cookie

```
value = token "." issued "." expires "." sig        (all base64url or decimal)
sig   = HMAC-SHA256(key, token "." issued "." expires)
key   = HMAC-SHA256(secret, effective_password_hash)
```

Deriving the key from the password hash means any password change, from
the CLI or from the environment variable, ends every session with no
bookkeeping; rotating `secret` in `set-password` also covers setting the
same password again. Verification uses `hmac.compare_digest` and checks
`expires > now`. Alternative: a server-side session table. Rejected: more
state to persist, for a single-user tool whose only bulk revocation need is
covered by the password change.

### API tokens

`new_token()` = `"wosarcher_" + "".join(secrets.choice(BASE62) for _ in
range(36))` (about 214 bits). Stored as `sha256(token).hexdigest()`; a slow
hash is unnecessary for random tokens of this length. Lookup hashes the
presented token and compares against each stored hash with
`compare_digest`. `last_used` is written only when the stored value is
more than 60 seconds old, to avoid a file write per request. List output
masks as `wosarcher_••••<last4>`. IDs are `secrets.token_hex(4)`.

### Guard: one ASGI middleware

A pure ASGI middleware (not `BaseHTTPMiddleware`, which does not see
WebSocket scopes) applies, in order, for paths under `/api`:

1. **Host**: when authentication is disabled, the `Host` name must be
   `localhost`, `127.0.0.1`, or `[::1]` → else 403 `bad_host`.
2. **Origin**: for state-changing methods and WebSocket handshakes, an
   `Origin` header, when present, must equal `scheme://host` of the request
   (scheme `ws` maps to `http`, `wss` to `https`) or be in
   `auth.allowed_origins` → else 403 `bad_origin`.
3. **Content type**: for state-changing methods with a body
   (`content-length > 0` or chunked), `application/json`, or
   `multipart/form-data` for `POST /api/runs` → else 415.
4. **Authentication**: skip for `POST /api/login`; when enabled, accept a
   valid bearer token (`method = "token"`) or a valid cookie
   (`method = "cookie"`) → else 401 `unauthenticated`. When disabled,
   `method = "none"`.
5. **Token routes**: `/api/tokens*` with `method = "token"` → 403.

The result is stored in `scope["state"]["auth"]` for `GET /api/session`.
For a WebSocket scope, a rejection is sent as `websocket.close` with code
1008 before accept, which the server turns into an HTTP 403 handshake
response. Paths outside `/api` pass untouched.

### Login rate limiter

`LoginLimiter` keeps, per client IP, the failure timestamps of the last 60
seconds, `paused_until`, the next pause length (30 s, doubling to 900 s),
and the last failure time. `check(ip, now) -> retry_after | None`,
`fail(ip, now) -> attempts_left | retry_after`, `succeed(ip)`. Entries
older than 15 minutes without a failure are dropped on access, which also
resets the pause length. The clock is injected so tests do not sleep. The
client IP is `scope["client"][0]`; behind a local reverse proxy, uvicorn's
`proxy_headers` (enabled in `serve`) supplies the forwarded address from
trusted proxies only.

### Bind check

`serve` resolves settings, then `is_loopback(host)` (`ipaddress` for
literals, `localhost` by name) and refuses with exit code 2 when the host
is not loopback and no effective password hash exists.

### Tests

Server tests use `TestClient(app, base_url="http://127.0.0.1:8765")` so the
loopback Host check passes; the server-api fixture is updated accordingly.
scrypt in tests uses the real parameters (one hash per test module, cached
in a fixture) so tests check what production runs.

## Risks / Trade-offs

- [A stolen cookie stays valid until it expires] → Mitigation: changing the
  password ends all sessions; cookies are `HttpOnly` and `SameSite=Strict`;
  the design requires Tailscale or TLS on networks others can sniff.
- [Rate limiter state lost on restart] → Accepted: restarting needs access
  to the machine already.
- [All clients behind one proxy share one IP] → One user tool; the pause
  affects only login, and tokens are unaffected.
- [Origin missing passes] → Browsers always send `Origin` on cross-site
  state-changing requests and WebSocket handshakes, so only non-browser
  clients, which hold no ambient cookies, omit it.
- [`auth.json` readable by root and the owner] → Mode 0600; it holds only
  hashes and the session secret.
