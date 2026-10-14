# saved-presets Specification

## Purpose

Lets a client save, update, and delete user profiles and depth presets as
TOML files in the configuration directory, so tunings made in the web UI
can be reused by name like any hand-written profile or preset.

## Requirements

### Requirement: Saved names
A profile or depth preset saved through the API SHALL have a name matching
`^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$`. A name that does not match SHALL be
rejected with 422 `invalid_name`. The name `custom` SHALL be rejected for
both kinds, and the built-in depth names (`quick`, `standard`, `deep`,
`exhaustive`) for depths, with 422 `invalid_name` saying the name is
reserved. A new name equal, ignoring case, to an existing profile (for a
profile) or an existing depth preset (for a depth) SHALL be rejected with
409 `name_taken` naming the existing one.

#### Scenario: Path in a name
- **WHEN** a client posts `{"name": "../x", "from": "cloud"}` to `POST /api/profiles`
- **THEN** the response is 422 with `error = "invalid_name"` and no file is written

#### Scenario: Reserved depth name
- **WHEN** a client posts a depth named `Deep`
- **THEN** the response is 422 with `error = "invalid_name"` and the detail says `Deep` is reserved

#### Scenario: Taken ignoring case
- **WHEN** the profile `cloud` exists and a client posts a profile named `Cloud`
- **THEN** the response is 409 with `error = "name_taken"` naming `cloud`

### Requirement: Managed files
A profile or depth preset that the NixOS module wrote (listed in the
module's manifest `profiles/.nix-managed`) SHALL be managed: it SHALL NOT
be updated or deleted through the API, which SHALL answer 409 `managed`
saying the file is managed by the NixOS configuration. Built-in depth
presets SHALL NOT be updated or deleted either (409 `builtin`). Without a
manifest no file is managed. A managed profile MAY be the base of a new
profile.

#### Scenario: Update a managed profile
- **WHEN** the manifest lists `workstation.toml` and a client sends `PATCH /api/profiles/workstation`
- **THEN** the response is 409 with `error = "managed"` and the file is unchanged

#### Scenario: Delete a managed depth
- **WHEN** the manifest lists `../depths/wide.toml` and a client sends `DELETE /api/depths/wide`
- **THEN** the response is 409 with `error = "managed"`

#### Scenario: Save as from a managed profile
- **WHEN** the manifest lists `workstation.toml` and a client posts `{"name": "ws-fast", "from": "workstation"}`
- **THEN** the response is 201 and `profiles/ws-fast.toml` exists

### Requirement: Save a profile
`POST /api/profiles` SHALL accept `name`, `from` (an existing profile),
an optional `description`, and the edits a run request carries: `use`
(an entry name per block) and `llm` (the object of http-api "LLM options
in a run request"). It SHALL write `profiles/<name>.toml` holding the base
profile's own keys with the edits applied:
- `description`: the given one, else the base's;
- each block in `use` replaces that block in the base's `[use]`; blocks
  the base leaves out stay out;
- `llm.model` sets `[llm] model`; `llm.context_tokens` sets
  `[select] max_context_tokens`;
- `llm.context_window`, `llm.max_output_tokens`, `llm.reasoning.<step>`,
  and `llm.gap_context_tokens` set those keys in `[models."<id>"]`, merged
  over the base's table for `<id>`, where `<id>` is the edited model, else
  the base's `llm.model`, else the default model of the chosen llm entry.

The written file SHALL load as a profile (run-config "Keys a profile may
set"). The response SHALL be 201 with the new profile as `GET
/api/profiles` lists it. An unknown `from` SHALL answer 404
`profile_not_found`; an unknown entry in `use` SHALL answer 422 naming
`use.<block>` and that block's entries; an invalid `llm` field SHALL answer
422 naming `llm.<field>`.

#### Scenario: Save as with model tuning
- **WHEN** the profile `cloud` uses llm `openrouter` with `llm.model = "claude-sonnet-5-5"`, and a client posts `{"name": "cloud-rerank", "from": "cloud", "use": {"score": "rerank"}, "llm": {"reasoning": {"write": "high"}, "context_tokens": 120000}}`
- **THEN** `profiles/cloud-rerank.toml` has `cloud`'s description and other keys, `use.score = "rerank"`, `select.max_context_tokens = 120000`, and `models."claude-sonnet-5-5".reasoning.write = "high"`

#### Scenario: Base keys kept
- **WHEN** the base profile sets `search.language = "es"` and `run.gpu_policy = "exclusive"`
- **THEN** the saved profile sets both

#### Scenario: Unknown base
- **WHEN** a client posts `{"name": "x", "from": "nope"}`
- **THEN** the response is 404 with `error = "profile_not_found"`

### Requirement: Update a profile
`PATCH /api/profiles/{name}` SHALL accept an optional `description`,
`use`, and `llm`, and apply them to that profile's own file as "Save a
profile" applies edits to a base. It SHALL answer 200 with the updated
profile, 404 `profile_not_found` for an unknown name, and 409 `managed`
for a managed one.

#### Scenario: Save edits into the profile
- **WHEN** the user profile `low-vram` uses model `qwen3-14b` and a client sends `PATCH /api/profiles/low-vram` with `{"llm": {"max_output_tokens": 12288}}`
- **THEN** `profiles/low-vram.toml` has `models."qwen3-14b".max_output_tokens = 12288` and its other keys unchanged

### Requirement: Delete a profile
`DELETE /api/profiles/{name}` SHALL remove the profile's file and answer
204. It SHALL answer 404 `profile_not_found` for an unknown name, 409
`managed` for a managed one, and 409 `active_profile` for the active
profile (run-config "Profile selection"). Runs that used the profile
SHALL keep their records.

#### Scenario: Delete a saved profile
- **WHEN** a client deletes the user profile `cloud-rerank`, which is not active
- **THEN** the response is 204 and `GET /api/profiles` no longer lists it

#### Scenario: Active profile
- **WHEN** the stored default profile is `low-vram` and a client deletes it
- **THEN** the response is 409 with `error = "active_profile"` and the file still exists

### Requirement: Save a depth preset
`POST /api/depths` SHALL accept `name`, an optional `description`, and
`values` with `sub_queries`, `results_per_query`, `max_pages`,
`passages_per_query`, `rounds`, `queries_per_round` (the ranges of the
run request's `research`), and `words` (a positive integer, or null to
leave Length to the global default). It SHALL write `depths/<name>.toml`
with the description and the depth keys those values set, and answer 201
with the preset as `GET /api/depths` lists it. `PUT /api/depths/{name}`
SHALL accept the same `description` and `values` and replace a user
preset's file (200), answering 404 `depth_not_found` for an unknown name,
409 `builtin` for a built-in preset, and 409 `managed` for a managed one.
`DELETE /api/depths/{name}` SHALL remove a user preset's file (204) with
the same errors. Runs that used a preset SHALL keep their records.

#### Scenario: Save a depth
- **WHEN** a client posts `{"name": "wide", "description": "Your preset: 10 sub-queries, 1 round, 1,500 words.", "values": {"sub_queries": 10, "results_per_query": 12, "max_pages": 200, "passages_per_query": 8, "rounds": 1, "queries_per_round": 3, "words": 1500}}`
- **THEN** `depths/wide.toml` sets `plan.max_sub_queries = 10`, `search.max_results = 12`, `fetch.max_pages = 200`, `score.top_k = 8`, `research.rounds = 1`, `research.queries_per_round = 3`, and `write.words = 1500`, and `GET /api/depths` lists `wide` with source `user`

#### Scenario: Invalid value
- **WHEN** a client posts a depth with `"rounds": 9`
- **THEN** the response is 422 naming `values.rounds` and no file is written

#### Scenario: Update a built-in
- **WHEN** a client sends `PUT /api/depths/quick`
- **THEN** the response is 409 with `error = "builtin"`

### Requirement: Saved file safety
Each write SHALL go to a temporary file in the same directory (a name the
profile and preset listings do not match) that then replaces the target,
so a reader never sees a partial file. Written files SHALL have mode 0600,
and the `profiles/` and `depths/` directories SHALL be created when
missing. A name SHALL only ever address `profiles/<name>.toml` or
`depths/<name>.toml`.

#### Scenario: Mode
- **WHEN** a client saves the profile `cloud-rerank` on a daemon whose umask is 0022
- **THEN** `profiles/cloud-rerank.toml` has mode 0600
