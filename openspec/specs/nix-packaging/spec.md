# nix-packaging Specification

## Purpose

Builds wosarcher as a Nix package and runs it as a native NixOS service
whose data a host CLI can share, so the server and agents on the same
machine use one set of profiles, runs, caches, and secrets.

## Requirements

### Requirement: Flake package

The flake SHALL provide `packages.<system>.wosarcher` and
`packages.<system>.default` (the same package) for `x86_64-linux` and
`aarch64-linux`. The package SHALL contain the `wosarcher` client and the
`wosarcherd` daemon with the Python dependency versions recorded in
`uv.lock`, the built web UI, and the `pandoc` and `typst` commands that
report export uses. `wosarcherd serve` from the package SHALL serve the
packaged web UI without `server.static_dir` being set.

#### Scenario: Package runs without a checkout

- **WHEN** the user runs `nix run .#wosarcher -- --help` outside the repository
- **THEN** the command prints the `wosarcher` help and exits 0

#### Scenario: Packaged web UI is served

- **WHEN** `wosarcherd serve` from the package runs on a loopback address with no settings
- **THEN** `GET /` answers 200 with the web UI's `index.html`

#### Scenario: Report export works from the package

- **WHEN** a finished run is exported with `wosarcher export <run_id> --format pdf` against the packaged daemon
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
`services.wosarcher.enable = true`, the system SHALL run `wosarcherd serve`
from the package as the `wosarcher.service` systemd unit, as the system user
`wosarcher` with the primary group `wosarcher`, bound to
`services.wosarcher.host` and `services.wosarcher.port` (defaults
`127.0.0.1` and `8765`), and SHALL provide `wosarcher.socket`, a Unix
socket at `/run/wosarcher/api.sock` with mode 0660, owned by `wosarcher`
and group `wosarcher`, that starts the service on the first connection and
is passed to it as an inherited listener. The service SHALL keep its
configuration, runs, and caches under `/var/lib/wosarcher`, in `config/`,
`share/`, and `cache/`, used as `XDG_CONFIG_HOME`, `XDG_DATA_HOME`, and
`XDG_CACHE_HOME`. The service SHALL restart on failure, SHALL have no
capabilities and no way to gain privileges, SHALL see the file system
read-only except `/var/lib/wosarcher` and `/run/wosarcher`, and SHALL NOT
see home directories.

#### Scenario: Service starts

- **WHEN** a host enables the module and boots
- **THEN** `wosarcher.socket` is active, and after a connection `wosarcher.service` runs as user `wosarcher` and `GET /api/session` on the configured port answers

#### Scenario: Socket activation

- **WHEN** `autoStart = false`, the service is inactive, and a member runs `wosarcher runs`
- **THEN** the service starts and the command lists the runs

#### Scenario: Data stays in the state directory

- **WHEN** the service runs a run
- **THEN** the run directory is under `/var/lib/wosarcher/share/wosarcher/runs/`

### Requirement: Shared data for group members

The users listed in `services.wosarcher.users` SHALL be members of the
`wosarcher` group, which SHALL grant access to `/run/wosarcher/api.sock`
and nothing else. `/var/lib/wosarcher` and every directory and file under
it SHALL be owned by `wosarcher`, readable and writable by that user, and
inaccessible to the group and to others (directories 0750 at most, files
0600 at most, service umask 0077).

#### Scenario: Member reads a server run

- **WHEN** the service has finished a run and a member runs `wosarcher runs`
- **THEN** the run is listed

#### Scenario: Member cannot read the data directory

- **WHEN** a member lists `/var/lib/wosarcher/config/wosarcher` or reads `auth.json`
- **THEN** the access is refused

#### Scenario: Other users are kept out

- **WHEN** a user who is not a member connects to `/run/wosarcher/api.sock`
- **THEN** the connection is refused

#### Scenario: Server removes a CLI run

- **WHEN** a member has created a run over the socket and the run is deleted with `wosarcher runs` followed by `DELETE /api/runs/{id}`
- **THEN** the server removes the whole run directory and answers 204

### Requirement: Host CLI wrapper

The module SHALL put a `wosarcher` command on the system path that runs the
packaged client with `WOSARCHER_SOCKET=/run/wosarcher/api.sock`, and a
`wosarcherd` command that runs the packaged daemon with the service's
`XDG_CONFIG_HOME`, `XDG_DATA_HOME`, `XDG_CACHE_HOME`, and
`services.wosarcher.environment` values, for administration as the service
user (`sudo -u wosarcher wosarcherd auth set-password`). Neither wrapper
SHALL read `services.wosarcher.environmentFile`.

#### Scenario: Member CLI uses the server's profiles

- **WHEN** the module declares a profile `lan` and a member runs `wosarcher profile list`
- **THEN** `lan` is listed with source `user`

#### Scenario: Member CLI sees a redacted secret

- **WHEN** the declared profile sets `llm.api_key_file` and a member runs `wosarcher profile show lan`
- **THEN** the LLM API key appears redacted, not empty, and the member cannot read the secret file

#### Scenario: Admin sets the password

- **WHEN** an administrator runs `sudo -u wosarcher wosarcherd auth set-password`
- **THEN** `/var/lib/wosarcher/config/wosarcher/auth.json` is written with mode 0600 and the web UI requires the password

#### Scenario: Member CLI uses the server's secrets

- **WHEN** the daemon's profile resolves an LLM API key from a secret file and a member runs `wosarcher run "q" --until load --json`
- **THEN** the run is created with that key and the member never reads the key

#### Scenario: Non-member runs the wrapper

- **WHEN** a user outside the `wosarcher` group runs `wosarcher runs`
- **THEN** the command exits with 69 and names `/run/wosarcher/api.sock`

### Requirement: Declared profiles and hooks

`services.wosarcher.profiles` SHALL be an attribute set of profile names to
TOML-compatible values. Before the service starts, each entry SHALL be
written to `/var/lib/wosarcher/config/wosarcher/profiles/<name>.toml` as a
copy (never a link into the Nix store), owned by `wosarcher` with mode
0600. A profile that was declared before and is no longer declared SHALL be
removed. A profile file the module did not write SHALL be left alone.
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
environment variables for the service and the `wosarcherd` wrapper),
`services.wosarcher.environmentFile` (a path systemd reads at service
start, for variables that must not land in the Nix store; it may be
readable by root alone), and `services.wosarcher.autoStart` (default true;
when false the service is started by its socket or a socket proxy only).
Secrets SHALL NOT be accepted through any option whose value lands in the
Nix store, and the option descriptions SHALL say so. The `profiles` and
`environmentFile` descriptions SHALL name the `<x>_file` settings (for
example `llm.api_key_file`) as the way to pass a secret: a profile in the
Nix store holds the path of a secret file readable by the `wosarcher` user,
never the value.

#### Scenario: Allowed origin from the module

- **WHEN** `allowedOrigins = [ "https://wosarcher.example" ]` and a browser on that origin posts `/api/login`
- **THEN** the request is not refused with `bad_origin`

#### Scenario: Service not started at boot

- **WHEN** `autoStart = false` and the host boots
- **THEN** `wosarcher.service` is inactive until something connects to its socket or port

#### Scenario: Root-only environment file

- **WHEN** `environmentFile` is `0400 root:root`
- **THEN** the service starts with its variables and the `wosarcher` wrapper works for members
