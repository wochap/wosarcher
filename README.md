# wosarcher

A modular, scriptable research pipeline. Ask a question; wosarcher plans
sub-queries, searches the web (and your attached Markdown files), fetches
pages, ranks passages, and writes a report whose citations point to the exact
passages behind each claim.

It is used three ways:

- **CLI**: `wosarcher run "question"`, scriptable, with JSON output.
- **Web UI**: a real-time frontend over WebSocket, served by `wosarcher serve`.
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
uv run wosarcher serve       # API on http://127.0.0.1:8765/api
pnpm --dir web dev           # Vite dev server with hot reload
```

The Vite dev server proxies `/api` to `http://127.0.0.1:8765`; set
`WOSARCHER_DEV_API` to use another backend.

Use the CLI directly:

```sh
uv run wosarcher doctor                          # check every configured provider
uv run wosarcher run "What limits solid-state battery production?"
uv run wosarcher run "..." --until select --json # cited passages only, as JSON
uv run wosarcher run "..." --attach notes.md --sources both
uv run wosarcher runs                            # list runs
uv run wosarcher fork <run-id> --from write --tone critical  # rewrite only
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
frontend from the same origin. Each research run is a `wosarcher run`
subprocess, so a run survives a reload of the UI.

1. Build:

   ```sh
   uv sync --frozen --no-dev
   pnpm --dir web install --frozen-lockfile
   pnpm --dir web build      # writes web/dist
   ```

2. Configure providers in a profile (see Configuration) and check them:

   ```sh
   uv run --no-dev wosarcher profile use <name>
   uv run --no-dev wosarcher doctor
   ```

3. Set the admin password. It is required before the server may bind to
   anything other than loopback:

   ```sh
   uv run --no-dev wosarcher auth set-password
   ```

4. Start the server. Point `server.static_dir` at the absolute path of the
   build, because the default `web/dist` is relative to the working
   directory:

   ```sh
   WOSARCHER_SERVER__STATIC_DIR="$PWD/web/dist" \
     uv run --no-dev wosarcher serve --host 0.0.0.0 --port 8765
   ```

   Run it under a process supervisor (for example a systemd service) with
   `Restart=on-failure`.

**Security.** Single admin user, password stored as a scrypt hash, signed
`HttpOnly` session cookie, `Origin` checks, login rate limiting, and bearer
API tokens for scripts on other machines (`wosarcher auth new-token`). On
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
Select one with `--profile`, `WOSARCHER_PROFILE`, or `wosarcher profile use`.
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
provider = "llm"
base_url = "http://localhost:8080/v1"
model = "writer"
device = "laptop:gpu0"
```

Secrets never belong in profile files you share: pass them as environment
variables, for example `WOSARCHER_SCORE__API_KEY` or
`WOSARCHER_LLM__API_KEY`. They are redacted everywhere they are shown or
saved.

`wosarcher profile show` prints the resolved configuration;
`wosarcher doctor` checks each endpoint, its model, latency, and whether it
can unload.

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
src/wosarcher/   backend: models, ports, config, adapters, stages, runner, store, server, cli
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
