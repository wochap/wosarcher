# cli-client Specification

## Purpose

Defines how the `wosarcher` client reaches the daemon and what it never
holds, so a CLI user or an agent needs group membership or a token, never a
provider secret or access to the data directory.

## Requirements

### Requirement: Client holds no secret
The `wosarcher` command SHALL perform every action through the daemon's
HTTP API and SHALL NOT read profiles, provider secrets, `auth.json`, or any
run directory. The only credentials it may hold are a URL and an API token
given by the environment.

#### Scenario: Member without secrets
- **WHEN** a user who can reach the daemon's socket but cannot read the data directory or any secret file runs `wosarcher run "q" --until load --json`
- **THEN** the run is created and the command prints its JSON output

### Requirement: Connection
The client SHALL choose its connection in this order: when `WOSARCHER_URL`
is set, that `http://` or `https://` base URL with `Authorization: Bearer
$WOSARCHER_TOKEN` when `WOSARCHER_TOKEN` is set; otherwise the Unix socket
at `WOSARCHER_SOCKET` when set; otherwise `$XDG_RUNTIME_DIR/wosarcher.sock`
when `XDG_RUNTIME_DIR` is set, else `/run/wosarcher/api.sock`. Event
streams SHALL use the same connection as a WebSocket. When the connection
cannot be made, every command SHALL print one error naming the socket path
or URL and `wosarcherd`, and exit with 69. A 401 answer SHALL exit with 2
and say that `WOSARCHER_TOKEN` is missing or revoked.

#### Scenario: Socket default
- **WHEN** neither `WOSARCHER_URL` nor `WOSARCHER_SOCKET` is set, `XDG_RUNTIME_DIR=/run/user/1000`, and the daemon listens on `/run/user/1000/wosarcher.sock`
- **THEN** `wosarcher runs` lists the runs

#### Scenario: Remote with a token
- **WHEN** `WOSARCHER_URL=https://wosarcher.example` and `WOSARCHER_TOKEN` hold a valid token
- **THEN** `wosarcher run "q" --json` creates a run whose summary has origin `api` and the token's name

#### Scenario: Daemon not running
- **WHEN** nothing listens on the chosen socket and the user runs `wosarcher runs`
- **THEN** the command prints an error naming the socket path and `wosarcherd`, and exits with 69

#### Scenario: Revoked token
- **WHEN** `WOSARCHER_URL` is set and `WOSARCHER_TOKEN` was revoked
- **THEN** the command exits with 2 and the error names `WOSARCHER_TOKEN`

### Requirement: Token commands
`wosarcher tokens new <name>` SHALL create an API token through
`POST /api/tokens` and print the token once; `wosarcher tokens list` SHALL
print each token's ID, name, masked last 4 characters, creation and last
use; `wosarcher tokens revoke <id>` SHALL delete it. These commands SHALL
work over the socket and SHALL fail with 2 over a token-authenticated URL,
as the token routes refuse tokens.

#### Scenario: Create over the socket
- **WHEN** a member runs `wosarcher tokens new laptop` over the socket
- **THEN** a token starting `wosarcher_` is printed, and `wosarcher tokens list` then shows `laptop` with its masked value

#### Scenario: Token cannot mint tokens
- **WHEN** `WOSARCHER_URL` and `WOSARCHER_TOKEN` are set and the user runs `wosarcher tokens new x`
- **THEN** the command exits with 2 and the error says token routes need the socket or a browser session

### Requirement: Read-only commands through the API
`wosarcher profile list` and `wosarcher profile show [NAME]` SHALL use
`GET /api/profiles` (show prints the profile's resolved values the route
returns and never a secret); `wosarcher depth list` and `wosarcher depth
show NAME` SHALL use `GET /api/depths`; `wosarcher cancel <run_id>` SHALL
use `POST /api/runs/{id}/cancel` and print the result; `wosarcher schema`
SHALL print the contracts from the installed package without a connection.

#### Scenario: Profiles from the server
- **WHEN** the daemon's config directory has a user profile `lan` and a member runs `wosarcher profile list`
- **THEN** `lan` is listed with source `user`, and no profile file is read by the client

#### Scenario: Schema offline
- **WHEN** no daemon runs and the user runs `wosarcher schema`
- **THEN** the JSON Schema is printed and the exit status is 0
