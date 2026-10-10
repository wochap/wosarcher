# nix-packaging Specification

## Purpose

Builds wosarcher as a Nix package and runs it as a native NixOS service
whose data a host CLI can share, so the server and agents on the same
machine use one set of profiles, runs, caches, and secrets.

## Requirements

### Requirement: Flake package

The flake SHALL provide `packages.<system>.wosarcher` and
`packages.<system>.default` (the same package) for `x86_64-linux` and
`aarch64-linux`. The package SHALL contain the `wosarcher` command with the
Python dependency versions recorded in `uv.lock`, the built web UI, and the
`pandoc` and `typst` commands that report export uses. `wosarcher serve`
from the package SHALL serve the packaged web UI without
`server.static_dir` being set.

#### Scenario: Package runs without a checkout

- **WHEN** the user runs `nix run .#wosarcher -- --help` outside the repository
- **THEN** the command prints the `wosarcher` help and exits 0

#### Scenario: Packaged web UI is served

- **WHEN** `wosarcher serve` from the package runs on a loopback address with no settings
- **THEN** `GET /` answers 200 with the web UI's `index.html`

#### Scenario: Report export works from the package

- **WHEN** a finished run is exported with `wosarcher export <run_id> --format pdf` from the package
- **THEN** the PDF is written without `pandoc` or `typst` on the caller's `PATH`

### Requirement: Pinned dependency versions

Every direct dependency in `pyproject.toml`, runtime and dev, SHALL name one
exact version (`==`), and every dependency and dev dependency in
`web/package.json` SHALL name one exact version (no range operators). The
versions SHALL match `uv.lock` and `web/pnpm-lock.yaml`.

#### Scenario: A range in pyproject.toml

- **WHEN** a dependency in `pyproject.toml` is written as `fastapi>=0.142.2`
- **THEN** the change does not meet this requirement until it reads `fastapi==0.142.2`

### Requirement: NixOS service

The flake SHALL provide `nixosModules.default`. With
`services.wosarcher.enable = true`, the system SHALL run `wosarcher serve`
from the package as the `wosarcher.service` systemd unit, as the system user
`wosarcher` with the primary group `wosarcher`, bound to
`services.wosarcher.host` and `services.wosarcher.port` (defaults
`127.0.0.1` and `8765`). The service SHALL keep its configuration, runs, and
caches under `/var/lib/wosarcher`, in `config/`, `share/`, and `cache/`, used
as `XDG_CONFIG_HOME`, `XDG_DATA_HOME`, and `XDG_CACHE_HOME`. The service
SHALL restart on failure, SHALL have no capabilities and no way to gain
privileges, SHALL see the file system read-only except
`/var/lib/wosarcher`, and SHALL NOT see home directories.

#### Scenario: Service starts

- **WHEN** a host enables the module and boots
- **THEN** `wosarcher.service` is active, runs as user `wosarcher`, and `GET /api/session` on the configured port answers

#### Scenario: Data stays in the state directory

- **WHEN** the service runs a run
- **THEN** the run directory is under `/var/lib/wosarcher/share/wosarcher/runs/`

### Requirement: Shared data for group members

The users listed in `services.wosarcher.users` SHALL be members of the
`wosarcher` group. Every directory under `/var/lib/wosarcher` SHALL be
group-owned by `wosarcher`, setgid, and readable, writable, and searchable
by the group, with no access for others. Files and directories that the
service or the CLI wrapper create SHALL be readable and writable by the
group and inaccessible to others.

#### Scenario: Member reads a server run

- **WHEN** the service has finished a run and a member runs `wosarcher runs`
- **THEN** the run is listed

#### Scenario: Server removes a CLI run

- **WHEN** a member has created a run with the CLI and the run is deleted with `DELETE /api/runs/{id}`
- **THEN** the server removes the whole run directory and answers 204

#### Scenario: Other users are kept out

- **WHEN** a user who is not a member lists `/var/lib/wosarcher`
- **THEN** the listing is refused

### Requirement: Host CLI wrapper

The module SHALL put a `wosarcher` command on the system path that runs the
packaged CLI with the service's `XDG_CONFIG_HOME`, `XDG_DATA_HOME`, and
`XDG_CACHE_HOME`, the service's `services.wosarcher.environment` values,
the variables of `services.wosarcher.environmentFile` when it is set, and a
file creation mask that keeps new files group-writable. When the
environment file is set but the caller cannot read it, the command SHALL
exit non-zero with a message naming the file and the `wosarcher` group,
before running the CLI.

#### Scenario: Member CLI uses the server's profiles

- **WHEN** the module declares a profile `lan` and a member runs `wosarcher profile list`
- **THEN** `lan` is listed with source `user`

#### Scenario: Member CLI uses the server's secrets

- **WHEN** the environment file sets `WOSARCHER_LLM__API_KEY` and a member runs `wosarcher profile show`
- **THEN** the LLM API key appears redacted, not empty

#### Scenario: Non-member runs the wrapper

- **WHEN** a user outside the `wosarcher` group runs `wosarcher runs` and an environment file is set
- **THEN** the command exits non-zero and names the environment file and the `wosarcher` group

### Requirement: Declared profiles and hooks

`services.wosarcher.profiles` SHALL be an attribute set of profile names to
TOML-compatible values. Before the service starts, each entry SHALL be
written to `/var/lib/wosarcher/config/wosarcher/profiles/<name>.toml` as a
copy (never a link into the Nix store), readable by the group. A profile
that was declared before and is no longer declared SHALL be removed. A
profile file the module did not write SHALL be left alone.
`services.wosarcher.hooks` SHALL be written the same way to
`/var/lib/wosarcher/config/wosarcher/hooks.toml`; when it is empty, a
`hooks.toml` written by the module SHALL be removed.

#### Scenario: Dropped profile is removed

- **WHEN** a profile `old` is removed from `services.wosarcher.profiles` and the system switches
- **THEN** `profiles/old.toml` no longer exists and a hand-made `profiles/mine.toml` still does

#### Scenario: Hooks file from the module

- **WHEN** `services.wosarcher.hooks.on_finish` holds one entry with a `url`
- **THEN** `hooks.toml` holds one `[[on_finish]]` table with that `url`

### Requirement: Service configuration options

The module SHALL offer `services.wosarcher.package`,
`services.wosarcher.allowedOrigins` (passed to the server as
`auth.allowed_origins`), `services.wosarcher.environment` (extra
environment variables for the service and the wrapper),
`services.wosarcher.environmentFile` (a path read at service start, for
secrets), and `services.wosarcher.autoStart` (default true; when false the
unit is not started at boot, for socket proxies that start it on demand).
Secrets SHALL NOT be accepted through any option whose value lands in the
Nix store, and the option descriptions SHALL say so.

#### Scenario: Allowed origin from the module

- **WHEN** `allowedOrigins = [ "https://wosarcher.example" ]` and a browser on that origin posts `/api/login`
- **THEN** the request is not refused with `bad_origin`

#### Scenario: Service not started at boot

- **WHEN** `autoStart = false` and the host boots
- **THEN** `wosarcher.service` is inactive until something starts it
