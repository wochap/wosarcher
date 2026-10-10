# wosarcher

A modular, scriptable research pipeline. Ask a question; wosarcher plans
sub-queries, searches the web (and your attached Markdown files), fetches
pages, ranks passages, and writes a report whose citations point to the exact
passages behind each claim.

One daemon, `wosarcherd`, holds the provider secrets and the data and runs
every run. It is used three ways, all through its API:

- **CLI**: `wosarcher run "question"`, a client of the daemon, scriptable,
  with JSON output. It holds no secret: it reaches the daemon over a local
  Unix socket, or a remote one with `WOSARCHER_URL` and an API token in
  `WOSARCHER_TOKEN`.
- **Web UI**: a real-time frontend over WebSocket, served by `wosarcherd serve`.
- **Agents**: a skill (`skill/SKILL.md`) that teaches coding agents to call
  the CLI for cited context.

Every model and service sits behind HTTP, so each one can run on this
machine, on another machine in the local network, or in the cloud, chosen per
run by a configuration profile.

## Pipeline

```
query ─► initial search ─► plan ─► search ─► fetch ─┐
                                                    ├─► chunk ─► prefilter ─► score ─► select ─► write
attachments ─► load ────────────────────────────────┘
```

Stages run as phases across all sub-queries, so GPU stages (embeddings,
reranker, writer) run one after another in large batches. On a small GPU,
models can be unloaded between phases.

| Stage | Providers |
|---|---|
| search | SearXNG |
| fetch | Firecrawl (HTML and PDF) |
| prefilter | OpenAI-compatible embeddings, built-in BM25, or none |
| score | Cohere/Jina-style reranker, TypeSafe Jev, or built-in BM25 |
| plan, write | any OpenAI-compatible chat API |

The full design is in [docs/design.md](docs/design.md).

## Stack

| Part | Technology |
|---|---|
| Backend | Python 3.13, uv, Pydantic v2, httpx, Typer, Rich, FastAPI, Uvicorn, markdown-it-py |
| Frontend | Vite, React, TypeScript, react-markdown, Phosphor icons, Nocturne design system (vendored CSS) |
| Tooling | ruff, basedpyright (strict), pytest, Biome, Vitest, pnpm |
| Environment | Nix flake dev shell with direnv |
| Planning | OpenSpec (`openspec/`) |

## Requirements

- Nix with flakes (recommended): provides Python 3.13, uv, Node.js, and pnpm.
  Without Nix, install those yourself.
- Reachable providers, configured in a profile (see Configuration):
  - a SearXNG instance with the JSON format enabled,
  - a Firecrawl instance (self-hosted or the cloud API),
  - an OpenAI-compatible LLM endpoint,
  - optionally an embeddings endpoint, a reranker endpoint (for example
    llama-server with `--rerank`), or a TypeSafe API key for Jev.

## Development

```sh
git clone <repo> wosarcher && cd wosarcher
direnv allow                 # or: nix develop

uv sync                      # backend dependencies, including dev tools
pnpm --dir web install       # frontend dependencies
```

Run the backend and the frontend dev server in two terminals:

```sh
uv run wosarcherd serve      # API on http://127.0.0.1:8765/api and $XDG_RUNTIME_DIR/wosarcher.sock
pnpm --dir web dev           # Vite dev server with hot reload
```

The Vite dev server proxies `/api` to `http://127.0.0.1:8765`; set
`WOSARCHER_DEV_API` to use another backend.

Use the CLI client against the running daemon:

```sh
uv run wosarcher doctor                          # the daemon checks every configured provider
uv run wosarcher run "What limits solid-state battery production?"
uv run wosarcher run "..." --until select --json # cited passages only, as JSON
uv run wosarcher run "..." --attach notes.md --sources both
uv run wosarcher run "..." --allow-domain gob.pe --block-domain facebook.com  # domain filter
uv run wosarcher run "..." --rounds 2 --queries-per-round 6  # follow-up searches per round
uv run wosarcher run "..." --search-language es-PE  # SearXNG search language
uv run wosarcher runs                            # list runs
uv run wosarcher fork <run-id> --from write --tone critical  # rewrite only
uv run wosarcherd run "..." --until select --json  # the engine in this process, without a daemon
```

Checks:

```sh
scripts/check                # fast: format, lint, architecture layering
scripts/check --fix          # apply formatting and safe lint fixes first
scripts/check --full         # adds type checks, pytest, tsc, Vitest, type drift check
```

`scripts/check` must pass before any work is finished. Rules for
contributors and coding agents are in [docs/development.md](docs/development.md).
After changing a Pydantic contract, regenerate the frontend types with
`pnpm --dir web gen:types`.

New features start as OpenSpec changes (`/opsx:propose`), are implemented
with `/opsx:apply`, and archived with `/opsx:archive`.

## Production

wosarcher is a single Python process that serves the API and the built
frontend from the same origin. Each research run is a `wosarcherd run`
subprocess, so a run survives a reload of the UI.

1. Build:

   ```sh
   uv sync --frozen --no-dev
   pnpm --dir web install --frozen-lockfile
   pnpm --dir web build      # writes web/dist
   ```

2. Configure providers in a profile (see Configuration) and check them:

   ```sh
   uv run --no-dev wosarcherd profile use <name>
   uv run --no-dev wosarcherd doctor
   ```

3. Set the admin password. It is required before the server may bind to
   anything other than loopback:

   ```sh
   uv run --no-dev wosarcherd auth set-password
   ```

4. Start the server. Point `server.static_dir` at the absolute path of the
   build, because the default `web/dist` is relative to the working
   directory:

   ```sh
   WOSARCHER_SERVER__STATIC_DIR="$PWD/web/dist" \
     uv run --no-dev wosarcherd serve --host 0.0.0.0 --port 8765
   ```

   Run it under a process supervisor (for example a systemd service) with
   `Restart=on-failure`.

**Logs.** The server logs to standard error: each run's lifecycle (queued,
started, done, failed, cancelled, with its run ID) and every line a run
process prints to standard error, prefixed with `run <run-id>: `. Watch them
with `journalctl -u <service> -f` or `docker logs -f wosarcher`, and set the
level with `server.log_level` (`debug`, `info`, `warning`, `error`; for
example `WOSARCHER_SERVER__LOG_LEVEL=warning`). One run's events, also while
it runs:

```sh
wosarcher logs <run-id> --follow
```

### Docker

The `Dockerfile` builds one image (about 400 MB) with the daemon, the CLI
client, the built web UI, and pinned pandoc and Typst binaries for PDF and Word export. Everything that changes at runtime (profiles, password
hash, tokens, runs, caches) lives under `/data`.

```sh
docker build -t wosarcher .

# Admin password hash, for WOSARCHER_AUTH__PASSWORD_HASH (keep it in your secrets):
docker run --rm -it wosarcher wosarcherd auth set-password --print

docker run -d --name wosarcher \
  -p 8765:8765 \
  -v wosarcher:/data \
  -e WOSARCHER_AUTH__PASSWORD_HASH='scrypt$...' \
  -e WOSARCHER_PROFILE=desktop \
  wosarcher
```

- **Profiles**: put them in the volume at `/data/config/wosarcher/profiles/`,
  or pass settings as `WOSARCHER_*` environment variables.
- **Provider URLs**: inside a container, `localhost` is the container itself.
  Use LAN or Tailscale addresses in profiles, or run with `--network=host`
  (then drop `-p` and bind with `--host <address>`).
- **CLI in the container**: `docker exec wosarcher wosarcher doctor`,
  `docker exec wosarcher wosarcher runs` (over the daemon's socket in
  `/tmp`). From another machine: `WOSARCHER_URL=http://host:8765
  WOSARCHER_TOKEN=... wosarcher runs`.
- **Update**: rebuild (or pull) the image and recreate the container; the
  `/data` volume keeps all state.

On NixOS, prefer the module below.

### NixOS

The flake exports `nixosModules.default`, which runs the daemon as the
native `wosarcher.service`, activated by `wosarcher.socket`
(`/run/wosarcher/api.sock`), and puts on the system path a `wosarcher`
client for that socket and a `wosarcherd` wrapper for the service user:

```nix
{
  inputs.wosarcher.url = "github:wochap/wosarcher";

  outputs = { nixpkgs, wosarcher, ... }: {
    nixosConfigurations.host = nixpkgs.lib.nixosSystem {
      modules = [
        wosarcher.nixosModules.default
        {
          services.wosarcher = {
            enable = true;
            users = [ "alice" ];                  # joins the wosarcher group
            environmentFile = "/run/secrets/wosarcher.env";
            environment.WOSARCHER_PROFILE = "lan";
            profiles.lan = {
              llm.base_url = "http://desktop.lan:8080/v1";
            };
            # allowedOrigins = [ "https://wosarcher.example" ];
          };
        }
      ];
    };
  };
}
```

- **Data** lives in `/var/lib/wosarcher` (`config/`, `share/`, `cache/`),
  owned by `wosarcher`, directories 0700 and files 0600: no one else reads
  it.
- **Group members** (`services.wosarcher.users`; log in again after the
  switch) may use the socket and nothing else: `wosarcher runs`,
  `wosarcher run ...` go through the daemon, which holds the secrets.
- **Secrets** go in `environmentFile` (API keys,
  `WOSARCHER_AUTH__PASSWORD_HASH`), read by systemd alone (it may be `0400
  root:root`), or in files named by `<x>_file` settings and readable by the
  `wosarcher` user; never in `environment` or `profiles`, which land in the
  Nix store.
- **Password**: `sudo -u wosarcher wosarcherd auth set-password`.
- **On demand**: with `autoStart = false` the unit starts on the first
  connection to its socket, or when a socket proxy starts it.

Moving from the container: the existing `/var/lib/wosarcher` is owned by
uid 10001. Before the first start of the service, run once as root:

```sh
chown -R wosarcher:wosarcher /var/lib/wosarcher
```

Setting `users.users.wosarcher.uid = 10001` avoids it; the service removes
group and other access from the data on each start.

**Reverse proxy.** The server trusts `X-Forwarded-For` and
`X-Forwarded-Proto` only from the addresses in `server.forwarded_allow_ips`
(default `["127.0.0.1"]`). Without the proxy's address there, every
state-changing request from the browser answers 403 `bad_origin`, because
the server sees `http` while the browser sends an `https` origin. Set it to
the address the proxy connects from:

- Caddy on the Docker host, container published with `-p`: the bridge
  gateway, usually
  `-e WOSARCHER_SERVER__FORWARDED_ALLOW_IPS='["172.17.0.1"]'` (check with
  `docker network inspect bridge`).
- Caddy in the same Compose network: that network's subnet, for example
  `'["172.18.0.0/16"]'`.
- Caddy on the host and the container with `--network=host`: keep
  `127.0.0.1`.

Never use `"*"` unless nothing but the proxy can reach the server's port: it
lets any client set its own address and scheme. A minimal Caddyfile:

```
wos.lan {
    reverse_proxy 127.0.0.1:8765
}
```

**Security.** Single admin user, password stored as a scrypt hash, signed
`HttpOnly` session cookie, `Origin` checks, login rate limiting, and bearer
API tokens for scripts on other machines (`wosarcher tokens new`). On
plain HTTP the password and cookie can be read by anyone on the network: put
the server behind Tailscale or a TLS reverse proxy (for example Caddy), and
never expose it to the internet.

## Configuration

Settings are resolved with this precedence, lowest first:

1. built-in defaults,
2. the active profile,
3. environment variables (`WOSARCHER_` prefix, `__` for nesting, for
   example `WOSARCHER_SCORE__PROVIDER=jev`),
4. command-line overrides (`--set score.top_k=12`) or request fields.

**Profiles** are TOML files. Built-in ones are `workstation` (default),
`low-vram`, and `cloud`. Your own go in `$XDG_CONFIG_HOME/wosarcher/profiles/`
(`~/.config/wosarcher/profiles/`); a file with a built-in's name replaces it.
Select one with `--profile`, `WOSARCHER_PROFILE`, or `wosarcherd profile use`.
Changing a profile never needs a restart: each run reads it when it starts.

Example: embeddings and reranker on another machine, writer on this one.

```toml
# ~/.config/wosarcher/profiles/desktop.toml
[run]
gpu_policy = "shared"           # "exclusive" unloads models between phases

[search]
provider = "searxng"
base_url = "http://localhost:8888"

[fetch]
provider = "firecrawl"
base_url = "http://localhost:3002/v1"

[prefilter]
provider = "embeddings"
base_url = "http://desktop.lan:8002/v1"
model = "embeddings"
device = "desktop:gpu0"

[score]
provider = "rerank"
base_url = "http://desktop.lan:8001/v1"
model = "reranker"
device = "desktop:gpu0"
release = "llama-swap"          # none | llama-swap | ollama

[llm]
provider = "openai"
base_url = "http://localhost:8080/v1"
model = "writer"
device = "laptop:gpu0"
```

Secrets never belong in profile files you share: pass them as environment
variables, for example `WOSARCHER_SCORE__API_KEY` or
`WOSARCHER_LLM__API_KEY`. They are redacted everywhere they are shown or
saved.

**Provider quirks.**

- `llm.max_tokens_field`: the request field for the output limit,
  `max_completion_tokens` (default) or `max_tokens` for servers that need
  the older field (for example an Ollama build that ignores
  `max_completion_tokens`).
- `llm.reasoning.plan`, `llm.reasoning.gap`, `llm.reasoning.write`: thinking
  per step, `none` (default: `reasoning_effort: "none"` and an exact output
  limit), `low`, `medium`, `high` (`reasoning_effort` and no limit; the
  server sets the budget), or `default` (neither field, for servers that
  reject `reasoning_effort`). Per run: `--plan-thinking`, `--gap-thinking`,
  `--write-thinking`, and `--model`.
- `score.rerank_scale`: `auto` (default), `probability`, or `logit`. Logit
  scores from a reranker are mapped through a sigmoid before thresholds and
  display; `auto` detects the scale per run.
- `retry_budget` (every provider block): seconds a call may spend waiting
  between retries on 429/502/503/504/529, default 60; `0` disables retries.

`wosarcher profile show` prints the resolved configuration the daemon uses;
`wosarcher doctor` (or `wosarcherd doctor` locally) checks each endpoint, its model, latency, and whether it
can unload. It warns when the LLM server's context (llama-server `-c`) is
below `llm.context_window`.

**Paths.**

| What | Default |
|---|---|
| Profiles, password hash, tokens, server settings | `$XDG_CONFIG_HOME/wosarcher/` |
| Runs | `$XDG_DATA_HOME/wosarcher/runs` (`run.runs_dir`) |
| Page and embedding cache | `$XDG_CACHE_HOME/wosarcher` (`run.cache_dir`) |

Each run directory holds every intermediate artifact (`plan.json`,
`hits.jsonl`, `pages.jsonl`, `chunks.jsonl`, `scores.jsonl`,
`context.json`, `report.md`, `events.jsonl`, `costs.json`), so runs can be
inspected with `jq`, forked from any stage, and replayed by the evaluation
harness in `evals/`.

## Agent skill

Copy or symlink `skill/` into your agent's skills directory as `wosarcher/`.
It documents `wosarcher run "<query>" --until select --json` for cited
context and the full-report mode.

## Repository layout

```
src/wosarcher/   backend: models, ports, config, adapters, stages, runner, store, server, daemon, cli (client)
web/             frontend (Vite + React)
tests/           backend tests (fakes only, no network)
evals/           replay harness for comparing prefilters and scorers
skill/           agent skill
scripts/         check scripts and the architecture rule table
design/          Claude Design handoff bundle: the UI source of truth
docs/            design, development guide, frontend inventory
openspec/        specs and change history
```

## License

MIT. See [LICENSE](LICENSE).
