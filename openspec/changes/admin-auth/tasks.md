# Tasks

## 1. Configuration and layering

- [ ] 1.1 Add `AuthConfig(password_hash: SecretStr | None = None, session_days: int = 30, allowed_origins: list[str] = [])` as `Settings.auth` in `config.py`; verify `tests/test_config.py::test_auth_defaults` and a test that `WOSARCHER_AUTH__PASSWORD_HASH` resolves and is redacted as `***`
- [ ] 1.2 Add `"auth": {"config"}` to `ALLOWED` in `scripts/check_architecture.py` and add `auth` to the `server` and `cli` entries (reason: shared by CLI and server without importing FastAPI into the CLI); verify `scripts/check` passes
- [ ] 1.3 Add `LoginRequest`, `SessionInfo`, `TokenInfo`, `TokenCreate`, `TokenCreated`, and `LoginError` (design.md, Modules) to `models.py` and include them in `wosarcher schema`; verify round-trip tests in `tests/test_models.py` and a test that the schema output has a definition for each

## 2. auth.py (standard library only)

- [ ] 2.1 Implement `hash_password` and `verify_password` with `hashlib.scrypt` (n=2**15, r=8, p=1, dklen=32, maxmem=64 MiB) and the `scrypt$15$8$1$salt$key` format; verify `tests/auth/test_password.py::test_round_trip`, `::test_wrong_password`, `::test_params_read_from_hash`, `::test_salt_differs`
- [ ] 2.2 Implement `new_token` and `hash_token`; verify `tests/auth/test_tokens.py::test_format` (`wosarcher_` plus 36 base62 characters) and `::test_unique`
- [ ] 2.3 Implement `sign_session` and `verify_session` with the key derived from the secret and the password hash; verify `tests/auth/test_session.py::test_valid`, `::test_tampered_expiry`, `::test_expired`, `::test_new_hash_invalidates`, `::test_new_secret_invalidates` (spec: Session cookie, Password change ends sessions)
- [ ] 2.4 Implement `AuthStore` (mtime reload, flock, temp file plus rename with mode 0600, env hash precedence, token add/list/revoke/touch with the 60 s last-used rule); verify `tests/auth/test_store.py::test_mode_0600`, `::test_reload_on_change`, `::test_env_hash_wins`, `::test_last_used_throttled`, `::test_revoke_unknown_id`

## 3. CLI

- [ ] 3.1 Create `cli/auth.py` with the `auth` sub-app registered in `cli/__init__.py`, and add `wosarcher auth set-password [--print]` (prompt twice, minimum 8 characters, new secret, env warning); verify `tests/auth/test_cli.py::test_set_password_stores_hash`, `::test_mismatch_stores_nothing`, `::test_print_does_not_store`, `::test_env_warning` (spec: Password storage)
- [ ] 3.2 Add `wosarcher auth new-token <name>`, `list-tokens`, `revoke-token <id>`; verify `tests/auth/test_cli.py::test_token_lifecycle` (printed once, listed masked, revoked) (spec: API tokens)
- [ ] 3.3 Add the loopback bind check to `wosarcher serve` in `cli/serve.py`; verify `tests/test_cli_serve.py::test_lan_without_password_refused`, `::test_lan_with_password_starts`, `::test_localhost_name_allowed` with `uvicorn.run` patched (spec: Loopback bind without a password)

## 4. Server guard

- [ ] 4.1 Update `tests/server/conftest.py` to use `base_url="http://127.0.0.1:8765"` and add an `auth_app` fixture with a password set in a temporary config directory; verify the existing server-api tests still pass
- [ ] 4.2 Implement `server/guard.py` Host and Origin checks for http and websocket scopes, install it in `create_app`; verify `tests/auth/test_guard.py::test_rebound_host_403`, `::test_cross_site_post_403`, `::test_same_origin_passes`, `::test_missing_origin_passes`, `::test_allowed_origins_setting`, `::test_cross_site_websocket_rejected` (spec: Origin check, Loopback Host without a password)
- [ ] 4.3 Add the content-type check; verify `tests/auth/test_guard.py::test_form_put_settings_415`, `::test_json_runs_post_415`, `::test_multipart_runs_post_passes`, `::test_delete_without_body_passes` (spec: JSON-only bodies)
- [ ] 4.4 Add the authentication step (cookie or bearer, `POST /api/login` exempt, static paths untouched, `scope["state"]["auth"]`); verify `tests/auth/test_guard.py::test_no_credentials_401`, `::test_bearer_ok_updates_last_used`, `::test_revoked_token_401`, `::test_static_login_page_public`, `::test_websocket_without_cookie_rejected`, `::test_websocket_with_cookie_streams`, `::test_password_set_while_running` (spec: Protected routes, Authentication mode, API tokens)

## 5. Login, session, and tokens routes

- [ ] 5.1 Implement `LoginLimiter` with an injected clock; verify `tests/auth/test_limiter.py::test_attempts_left_counts_down`, `::test_fifth_failure_pauses_30`, `::test_backoff_doubles`, `::test_cap_15_minutes`, `::test_reset_after_quiet_period`, `::test_success_resets`, `::test_ips_independent` (spec: Login rate limit)
- [ ] 5.2 Implement `POST /api/login` (verification in a thread, cookie attributes, `Secure` for https, 401 with `attempts_left`, 429 with `retry_after` and `Retry-After`, 409 when disabled, failure logged without the password) in `server/login.py`; verify `tests/auth/test_login.py::test_right_password_sets_cookie`, `::test_wrong_password_attempts_left`, `::test_paused_right_password_429`, `::test_cookie_attributes_https`, `::test_auth_disabled_409`, `::test_failure_logged_without_password` (spec: Login, Session cookie)
- [ ] 5.3 Implement `POST /api/logout` and `GET /api/session`; verify `tests/auth/test_login.py::test_logout_clears_cookie`, `::test_session_cookie_since`, `::test_session_token_name`, `::test_session_disabled_none`, and `::test_password_change_ends_session` (spec: Logout and session info, Password change ends sessions)
- [ ] 5.4 Implement `server/tokens.py` routes and the token-auth 403 rule; verify `tests/auth/test_tokens_api.py::test_create_returns_token_once`, `::test_list_masked`, `::test_delete_204_and_404`, `::test_token_cannot_mint_403` (spec: API tokens)

## 6. Documentation and checks

- [ ] 6.1 Update docs/design.md "Authentication" and "Server": `/api` prefix and `POST /api/login`, behaviour without a password (loopback only, Origin and Host checks), token routes need a browser session, pause 30 s doubling to 15 min, `auth.json` contents, `set-password --print`; verify by reading the sections against the code
- [ ] 6.2 Verify `scripts/check --full` passes and `openspec validate admin-auth --strict` passes
