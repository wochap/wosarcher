# catalog-structure Specification

## Purpose

Defines the structure record that drives a catalog run (fields and their
types, required and volatile marks, child relation, seeds, leaf types, expand
mode, limits, language), its validation, the `draft` stage that checks or
derives it, and the draft route.

## Requirements

### Requirement: Structure record
A catalog run SHALL have a structure with:
- `fields`: a list of record fields, each with `name` (matching
  `^[a-z][a-z0-9_]{0,39}$`, unique in the list), `type` (`text`, `slug`,
  `url`, `date`, `enum`, or `ref`), `required` (boolean, default false),
  and `volatile` (boolean, default false; `text` fields only);
- `relation`: the child relation, a non-empty phrase of at most 200
  characters, written in the sources' language;
- `seeds`: one or more seeds, each with `name` (non-empty), `type` (one of
  the enum values), and `url` (optional; an `http` or `https` URL);
- `leaf_types`: a list of enum values (default empty);
- `expand`: `links`, `search`, or `both` (default `both`);
- `limits`: `max_depth` (1 to 10, default 3), `max_nodes` (1 to 5000,
  default 200), and `pages_per_node` (1 to 10, default 2);
- `language`: a search language (http-api "Create a run") or empty;
- `output`: `table` (default), `report`, or `both` (catalog-report
  "Output option").

The fields SHALL include exactly one `enum` field, whose `values` (one to
40 distinct non-empty strings) are the node types; at most one `slug`
field; at most one `ref` field (the parent reference); and at least one
required `text` field, the first of which is the **name field**. A
`volatile` field SHALL have a `date` field named in its `dated_by`, which
receives the date of the page its value came from. The structure SHALL
serialise to JSON and parse back to an equal value, and unknown keys
SHALL be rejected naming the key.

#### Scenario: Valid structure
- **WHEN** a structure has the fields `id` (slug), `name` (text, required), `type` (enum with seven values), `parent_id` (ref), `head_name` (text, volatile, dated by `verified_on`), `verified_on` (date), and `website` (url), the relation "organismos públicos adscritos o dependientes", six seeds, leaf types `regional_government` and `office`, expand `both`, and limits 3, 200, 2
- **THEN** it is accepted, its name field is `name`, and its slug field is `id`

#### Scenario: Two enum fields
- **WHEN** a structure has two fields of type `enum`
- **THEN** it is rejected with an error naming both fields

#### Scenario: Seed type outside the enum
- **WHEN** a seed has type `agency` and the enum values do not include it
- **THEN** the structure is rejected with an error naming the seed and `agency`

#### Scenario: Volatile without a date field
- **WHEN** a `text` field is volatile and names no `dated_by`, or names a field that is not of type `date`
- **THEN** the structure is rejected with an error naming the field

#### Scenario: Bad field name
- **WHEN** a field is named `Head Name`
- **THEN** the structure is rejected with an error naming it and the pattern

#### Scenario: Output default
- **WHEN** a structure leaves `output` unset
- **THEN** it resolves to `table`

#### Scenario: Invalid output
- **WHEN** a structure sets `output` to `summary`
- **THEN** it is rejected with an error naming `output` and the three values

### Requirement: Draft stage
The `draft` stage SHALL run first after `load` in a catalog run. When the
run request carries a structure, `draft` SHALL validate it (Requirement:
Structure record), write it as `structure.json`, and seed the frontier
(catalog-crawl "Frontier") with one node per seed at depth 0, status
`discovered`, `found_by` `seed`, and the seed's URL when it has one. An
invalid supplied structure SHALL fail the run at `draft` with the
validation error.

When the request carries no structure, `draft` SHALL make one LLM call:
a system message from `prompts/draft.md` with only the brief, the default
limits, and the date substituted, and one user message with a data
preamble and a delimited block holding the attachment outlines
(research-planning "Attachment outline"), or nothing. The prompt SHALL
ask for `output` too: `report` when the brief asks a question or for a
summary, `table` when it asks for a list or data, `both` when it asks for
both. The reply SHALL be JSON in the structure's shape. The stage SHALL
read it, apply the defaults for absent optional keys, validate it, and
fail the run with `draft failed: <reason>` when the reply cannot be read
or is invalid. The derived structure SHALL be written as `structure.json`
and recorded in `request.json` as the run's structure. Outlines SHALL
never go through a template.

#### Scenario: Supplied structure
- **WHEN** a catalog run starts with a valid structure of six seeds
- **THEN** `draft` makes no LLM call, writes `structure.json`, and `nodes.jsonl` holds six nodes at depth 0 with status `discovered`

#### Scenario: Derived structure
- **WHEN** a catalog run starts with the brief only and the draft call replies with a valid structure of 12 fields and 4 seeds
- **THEN** `structure.json` holds that structure, `request.json` records it, and the frontier holds 4 nodes

#### Scenario: Unreadable draft reply
- **WHEN** the draft call replies with text that holds no JSON object
- **THEN** the run fails at `draft` with an error starting `draft failed:`

#### Scenario: Outline is data
- **WHEN** an attachment outline contains "ignore previous instructions"
- **THEN** that text appears only inside the delimited block of the user message

#### Scenario: Output proposed
- **WHEN** the brief reads "list every comisaría in Peru with its address and tell me how they are distributed by region" and the draft reply sets `output` `both`
- **THEN** `structure.json` has `output` `both`

### Requirement: Draft route
`POST /api/catalog/draft` SHALL accept a multipart form with a `request`
field holding JSON (`brief`, required and non-empty; optional `profile`,
`use`, and `llm` as http-api "Create a run" defines them) and zero or
more `attachments`. It SHALL run the draft call (Requirement: Draft
stage) with the resolved llm block, without creating a run, and answer
200 with the derived structure. A failed or unreadable call SHALL answer
502 `draft_failed` with the reason. The route SHALL need the same
authentication as `POST /api/runs`.

#### Scenario: Draft from the web form
- **WHEN** a client posts `request = {"brief": "Every public organization of the Peruvian state…"}`
- **THEN** the response is 200 with a structure whose fields, seeds, relation, and limits can be posted back as a run's `structure`

#### Scenario: Draft failed
- **WHEN** the llm provider is unreachable
- **THEN** the response is 502 with `error = "draft_failed"` and no run is created

### Requirement: Catalog reasoning levels
The `draft` stage's LLM call SHALL use the reasoning level
`llm.reasoning.draft`, and every `extract` call SHALL use
`llm.reasoning.extract`. Neither SHALL read `plan`, `gap`, or `write`.
Both default to `none`.

#### Scenario: Extract level
- **WHEN** a catalog run resolves `llm.reasoning.extract` to `low` and `llm.reasoning.gap` to `high`
- **THEN** every extraction call is made with reasoning `low`

#### Scenario: Draft level
- **WHEN** a catalog run resolves `llm.reasoning.draft` to `medium`
- **THEN** the draft call is made with reasoning `medium`
