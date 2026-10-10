# Development

Guidance for people and coding agents working on wosarcher.

## Read first

- `docs/design.md`: the reference design.
- `openspec/`: specs and changes. New work starts as an OpenSpec change
  (`/opsx:propose`), is implemented with `/opsx:apply`, and is archived with
  `/opsx:archive`.

## Environment

The Nix flake provides Python 3.13, uv, Node.js, and pnpm. With direnv, the
shell loads on `cd`; otherwise run `nix develop`.

uv uses the Nix Python; Python downloads are disabled
(`UV_PYTHON_DOWNLOADS=never`).

## Commands

```sh
uv sync                     # install backend dependencies
pnpm --dir web install      # install frontend dependencies

scripts/check               # fast sanity check; must pass before work is done
scripts/check --fix         # format and apply safe lint fixes, then check
scripts/check --full        # fast check, then type checks and tests
```

`scripts/check` runs `scripts/check-backend` and `scripts/check-frontend`
and skips a side that does not exist yet:

- Backend: `ruff format --check`, `ruff check`, and
  `scripts/check_architecture.py`, which enforces the ports-and-adapters
  layering: stages, models, ports, lexical, and prompts are pure (no
  adapters, store, runner, or I/O libraries); only `build`, `server`, and
  `cli` import adapters; adapters never import each other in any import form
  (`from wosarcher.adapters import x` and relative imports included), and
  `adapters/__init__.py` imports no adapter (no registry). Pure parts also
  may not use the standard library's file, process, and network modules
  (`os`, `io`, `subprocess`, `socket`, `shutil`, `tempfile`, `sqlite3`,
  `urllib.request`, `http.client`, `importlib`), `pathlib.Path` (pure path
  classes are fine), or the `open` and `__import__` builtins; `prompts` may
  use `importlib.resources` to read its own files. A new top-level module
  must be added to its `ALLOWED` table with the imports it may use. The
  script has its own tests in `tests/test_check_architecture.py`.
- Frontend: `biome check` (format and lint), plus design-token rules: no raw
  hex colors and no font families outside the Nocturne variables
  (`web/src/vendor/` is exempt).
- `--full` adds `basedpyright`, `pytest`, `tsc --noEmit`, and the frontend
  tests.

openspec-pipeline uses it as its gate: `--gate scripts/check`.

`scripts/dev-serve` runs this checkout in place of the NixOS service on
the same host: it reads the live `wosarcher.service` unit (environment and
secrets file) and the lazy proxy socket named by `WOSARCHER_DEV_SOCKET`
(default `wosarcher-proxy.socket`; address and port), stops them, copies
the Nix-managed profiles, runs, and caches into
`~/.local/state/wosarcher-dev` (one way: dev runs never reach the service;
and the service's `auth.json` on the first run; after that the dev server
keeps its own password, set with
`XDG_CONFIG_HOME=~/.local/state/wosarcher-dev/config uv run wosarcher auth
set-password`), builds the web UI (`--no-web` skips it), and serves on the
socket's port, so the nginx URL reaches the dev server. Exiting starts the
socket again. You must be in the `wosarcher` group; sudo is needed for
`systemctl` and for a secrets file the group cannot read.

## Nix package and module

`nix/` holds the package (`package.nix`, `web.nix`), the NixOS module
(`module.nix`), and its VM test (`test.nix`):

```sh
nix build .#wosarcher                       # the package
nix run .#wosarcher -- --help
nix build .#checks.x86_64-linux.nixos -L    # VM test (needs KVM, minutes)
```

`scripts/check --full` does not run the VM test; run it after changing
`nix/` or anything the service touches (file modes, `auth.py`, export).

Versions are exact in `pyproject.toml` and `web/package.json`. To upgrade:

- Python: change the `==` version in `pyproject.toml`, then `uv lock`.
- Web: change the version in `web/package.json`, then
  `pnpm --dir web install`. The Nix web build then fails with a hash
  mismatch for `wosarcher-web-pnpm-deps`; paste the `got:` hash into
  `hash` in `nix/web.nix`.

## Rules

- Maintainability and readability come first.
- Work is not finished until `scripts/check` passes. Fix the cause; never
  weaken the check, add ignores, or edit `ALLOWED` to silence a layering
  violation without a design reason.
- One adapter per file, aim for under 200 lines. Stages are pure functions:
  inputs and ports in, a model out; no file or event access.
- No globals, registries, generic decorators, or metaclass magic. `build.py`
  wires adapters from a dict.
- Prompts and tones live in `prompts/`. Scraped text is never passed through
  a template or `str.format`.
- Plain httpx; no LangChain.
- Every adapter has a fake. Tests never touch the network.
- New dependencies need a reason in the OpenSpec design.
- When a change refines the design, update `docs/design.md` in the same
  change.
- Frontend work matches the design bundle in `design/` (read
  `design/README.md` first). Use the vendored Nocturne `styles.css`
  variables and classes; never hard-code colors, fonts, or spacing the tokens
  already carry.
