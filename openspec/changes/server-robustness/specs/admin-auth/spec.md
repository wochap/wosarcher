## MODIFIED Requirements

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

## ADDED Requirements

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
