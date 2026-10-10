# Handoff: secret-sources

Status: explored, not proposed. No OpenSpec change exists yet and no code is
written. Start with `/opsx:propose secret-sources` (or `/opsx:explore` to
revisit the open points first).

## Goal

Let every secret setting be given as a file path or a command instead of the
secret value, so profiles can live in the Nix store and secrets never pass
through an environment file. This follows the convention used across
`~/nix-config` (for example vdirsyncer's `passwordCommand = [ cat file ]` in
`modules/nixos/desktop/wm-addons/vdirsyncer.nix`, and
`passwordSecret.sopsFile`/`sopsKey` on mail accounts in
`hosts/gdesktop/default.nix`).

```toml
# profile (can live in the Nix store: it holds a path, not the key)
[llm]
api_key_file = "/run/secrets/local-omniroute-secret-key"     # sops.secrets.<x>.path

[score]
api_key_command = ["pass", "show", "typesafe/api-key"]       # argv, no shell
```

## Agreed shape

- Every secret field `<x>` gets two siblings, `<x>_file` and
  `<x>_command`. At most one of the three may be set.
- Secret fields today (`src/wosarcher/config.py`): `api_key` on every
  provider block (`Provider`, line ~86: search, fetch, prefilter, score,
  llm) and `auth.password_hash` (line ~243). Both are `SecretStr`.
- `<x>_file`: read the file and strip one trailing newline.
- `<x>_command`: a TOML array (argv), run with no shell, stdin closed, and a
  timeout. It must exit 0; its stdout, with one trailing newline stripped,
  is the value.
- Environment variables work with no extra code, because `env_layer` maps
  `WOSARCHER_LLM__API_KEY_FILE=/run/...` to `llm.api_key_file`.
- The value is resolved once per process, when the configuration resolves,
  and kept as `SecretStr`. Server runs are child processes, so a rotated
  secret is picked up by the next run.
- Errors are `ConfigError`s that name the key and the file path or argv[0],
  never the output. The CLI exits 2 before creating the run.
- `profile show` prints the path or the command (not secret) and redacts any
  resolved value.

## Security rule (must be in the spec)

`RunCreate.set` and `PUT /api/settings` can set any field today. If they
could set `*_file` or `*_command`:

- `_command` gives any API caller command execution as the server user.
- `_file` plus a `base_url` override sends any file the server can read
  (for example `auth.json`) to a host the caller chooses.

So `*_file` and `*_command` are accepted only from profile files, the
environment, and the CLI's own `--set`. The API must reject them.

Pitfall: the server passes `RunCreate.set` to the child process as `--set`
flags (`server/staging.py:266` and `:297`), so the child cannot tell an API
override from a CLI one. The rejection must happen in the server, when it
validates `RunCreate.set` and the global settings, before staging. A
`ConfigError`-style 422 naming the key fits the existing API errors.

## Open points

1. Where the resolution code lives. `config` is not one of the pure parts in
   `scripts/check_architecture.py` (those are stages, models, ports,
   lexical, prompts), and it already reads TOML files, so running a
   subprocess there passes the layering check. The alternative is a small
   helper called from `resolve()`. Decide in the design; no `ALLOWED` edit
   should be needed either way.
2. The command timeout. A default of 10 seconds is suggested; `pass` with a
   GPG agent prompt may need more, or the timeout could be configurable.
3. run-hooks (`openspec/changes/run-hooks`) uses `env:NAME` for webhook
   `headers` and `secret`. When run-hooks is re-planned, give it the same
   `_file`/`_command` forms for one convention, or keep `env:` as well.

## Effect on the Nix side

- `nix/module.nix` (this repo): `environmentFile` can stay for other
  variables, but secrets no longer need it. The module docs should show the
  `api_key_file` pattern.
- `~/nix-config/modules/nixos/services/ai/wosarcher/default.nix`: the
  `wosarcher.env` sops template goes away. Each secret becomes a
  `sops.secrets.<name>` with `owner = "wosarcher"; group = "wosarcher";
  mode = "0440";`, and the generated profiles set, for example,
  `llm.api_key_file = config.sops.secrets.local-omniroute-secret-key.path`.
  That also fixes the current gap where the host's extra `environmentFile`
  reaches only the server and not the host CLI.

## Related context

- The CLI runs the whole pipeline itself (no server involved), so it needs
  every provider secret its profile uses: today `llm.api_key` (OmniRoute)
  and, with the Jev profiles, `score.api_key`.
- A separate idea is parked, not decided: make the server a daemon that owns
  every run and the secrets, with the CLI as a client over a unix socket
  (`/run/wosarcher/api.sock`, group `wosarcher`, `SO_PEERCRED` for origin).
  That would remove the shared-store group access and most of the
  cross-process slot code from `external-runs`. secret-sources is useful
  either way, since the daemon itself needs its secrets from somewhere.

## Non-goals

- Secret managers other than "a file" or "a command" (no native sops, Vault,
  or keyring client).
- Shell strings for commands.
- Changing which fields are secret.
