# catalog-crawl Specification

## Purpose

Grows a catalog run's frontier (`nodes.jsonl`) in waves: the `expand` stage,
per-node search and fetch with caps, node dedupe, stop rules, the
`wave.done` and `catalog.done` events, and resume and fork of a catalog run.

## Requirements

### Requirement: Frontier
A catalog run SHALL keep its nodes in `nodes.jsonl`, one line per node,
appended when found and rewritten when a status changes, with: `id` (the
node's slug, unique in the run), `name`, `type` (an enum value), `parent_id`
(null for seeds), `depth` (0 for seeds), `url` (null when unknown), `wave`
(the wave it was found in), `status` (`discovered`, `expanding`,
`extracted`, `failed`), `expanded` (true once its children were looked
for), `found_by` (`seed`, `links`, or `search`), `pages` (the source IDs
used for it), `flags` (strings), and `reason` (the failure reason, else
null). A node is **expandable** when its type is not a leaf type and its
depth is below `limits.max_depth`. Every `node.found` event SHALL be
emitted when the node is appended.

#### Scenario: Seed node
- **WHEN** the seed "Poder Ejecutivo" of type `power` with a URL is added
- **THEN** `nodes.jsonl` holds it with depth 0, `parent_id` null, `found_by` `seed`, status `discovered`, and `node.found` carries its id, name, type, depth, and URL

#### Scenario: Leaf node is not expandable
- **WHEN** `leaf_types` holds `office` and a node of type `office` is found at depth 1
- **THEN** the node is extracted but its `expanded` stays false and no children query is written for it

### Requirement: Waves
After `draft`, the stages `expand`, `search`, `fetch`, `chunk`, and
`extract` SHALL run as a loop, one pass per wave, until a stop rule holds
(Requirement: Stop rules), then `assemble` SHALL run once. Wave `k` SHALL
take every node with status `discovered`, in order of discovery, and mark
them `expanding`. Stage and page events of a catalog run SHALL carry the
wave number as their `round`. After each wave the runner SHALL emit
`wave.done` with the wave number, the nodes expanded, the nodes found, the
records extracted, and the nodes failed in it.

#### Scenario: Two waves
- **WHEN** the seeds are extracted in wave 1 and yield 14 children
- **THEN** wave 2 expands those 14 nodes, `wave.done` for wave 1 reports 6 expanded and 14 found, and the `stage.started` events of wave 2 carry `round` 2

#### Scenario: Room left by max nodes
- **WHEN** `limits.max_nodes` is 200, 190 nodes exist, and a wave's extractions name 25 new children
- **THEN** only the first 10 are added, each later child is dropped, and the wave's `wave.done` notes `dropped` 15

### Requirement: Expand stage
For each node of the wave, `expand` SHALL produce:
- the URL to fetch first: the node's `url` when set;
- a self query, ID `n<k>s`, text `"<name> <type>"` (the type's enum
  value), only when the node has no URL;
- a children query, ID `n<k>c`, text `"<name> <relation>"`, only when
  the node is expandable and `expand` is `search` or `both`.

Queries SHALL carry the node ID and the wave, and SHALL be appended to
`plan.json`. A wave with no query SHALL still run `fetch` for the nodes'
known URLs. With `expand` = `links`, no children query SHALL be written
and the extraction prompt SHALL allow children from the page's links;
with `search`, from the page text only; with `both`, both.

#### Scenario: Seed with URL and both
- **WHEN** the node "Presidencia del Consejo de Ministros" has a URL, is expandable, and `expand` is `both`
- **THEN** `expand` writes only the children query "Presidencia del Consejo de Ministros organismos públicos adscritos o dependientes" and lists the URL to fetch first

#### Scenario: Child without URL and links
- **WHEN** a node has no URL and `expand` is `links`
- **THEN** `expand` writes only its self query

### Requirement: Search and fetch per node
`search` SHALL run the wave's queries with the run's domain lists and
search language (source-collection "Search over queries"); each hit SHALL
carry the node ID of its query. `fetch` SHALL take, per node, at most
`limits.pages_per_node` pages in the order: the known URL, then the
children query's hits in rank order, then the self query's hits. A URL
already fetched in the run SHALL be reused for the node (its source ID
added to the node's `pages`) without a new fetch and without counting
again toward `fetch.max_pages`; it SHALL count toward the node's
`pages_per_node`. Counted pages (source-collection "Fetch page cap and
order") across all waves SHALL not exceed `fetch.max_pages`. A node whose
every fetch fails SHALL get status `failed` with reason `no page`. `chunk`
SHALL run on the wave's new pages only.

#### Scenario: Pages per node
- **WHEN** `pages_per_node` is 2, a node has a URL, and its children query found 8 hits
- **THEN** the node's URL and the first hit are fetched and its `pages` lists two source IDs

#### Scenario: Shared page
- **WHEN** two nodes' hits name the same URL in one wave
- **THEN** it is fetched once, both nodes list its source ID, and it counts once toward `fetch.max_pages`

#### Scenario: No page
- **WHEN** every fetch for a node fails
- **THEN** the node's status is `failed` with reason `no page`, `node.failed` is emitted, and the wave continues

### Requirement: Children and dedupe
Children returned by `extract` (catalog-extraction "Extract stage") SHALL
become nodes at the parent's depth plus one, with `found_by` `links` when
the child came with a URL from the page, else `search`, only while the
parent is expandable. A child SHALL be dropped as a duplicate when its
normalised name (NFD, case-folded, punctuation stripped, whitespace
collapsed) equals an existing node's, or its normalised URL
(data-contracts "URL normalisation") equals an existing node's URL. When
the duplicate names a parent other than the existing node's, the existing
node SHALL get the flag `parent: also listed under <parent name>`. A child
whose type is not an enum value SHALL get the first enum value and the
flag `type: <value> not in the structure`. At most `catalog.max_children`
children per node SHALL be added, in the reply's order. Seeds are never
duplicates of later children: a child matching a seed is the seed.

#### Scenario: Same agency under two ministries
- **WHEN** INEI is found under PCM in wave 2 and a wave-3 extraction of MEF names "Instituto Nacional de Estadística e Informática" again
- **THEN** no second node is added and INEI's flags hold "parent: also listed under Ministerio de Economía y Finanzas"

#### Scenario: Unknown type
- **WHEN** a child comes with type `programa` and the enum is `power, ministry, public_body, office`
- **THEN** the node gets type `power` and the flag "type: programa not in the structure"

#### Scenario: Too many children
- **WHEN** `catalog.max_children` is 50 and an extraction names 70 children
- **THEN** the first 50 are added and the node gets the flag "children: 20 beyond the limit dropped"

### Requirement: Stop rules
After each wave the run SHALL stop the loop, and `assemble` SHALL follow,
at the first of these in order:

| Condition | Stop reason |
|---|---|
| no node has status `discovered` | `frontier empty` |
| nodes reached `limits.max_nodes` and no node has status `discovered` | `max nodes` |
| counted pages reached `fetch.max_pages` | `page limit reached` |
| every extraction of the wave failed | `extract failed` |
| the user answered "No, assemble now" at a wave pause | `stopped by user` |

`max depth` is not a stop reason: nodes at `max_depth` are extracted and
not expanded, so the frontier empties. The run SHALL write `catalog.json`
(catalog-extraction "Assemble stage") with the reason and a note: "No
unexpanded nodes left after wave <k>." for `frontier empty`, "Max nodes
<n> reached." for `max nodes`, "Page limit <n> reached." for `page limit
reached`, "Every extraction of wave <k> failed." for `extract failed`,
and "Stopped by the user after wave <k>." for `stopped by user`. When
`max_depth` was not reached by any node, the note SHALL add " Max depth
<d> was not reached." An `extract failed` stop SHALL add the warning
`extract failed: <first reason>` and SHALL NOT fail the run.

#### Scenario: Frontier empty
- **WHEN** wave 5 finds no new node and every node is extracted or failed
- **THEN** the loop stops with `frontier empty`, `catalog.done` carries 5 waves, and the note reads "No unexpanded nodes left after wave 5. Max depth 3 was not reached." when no node is at depth 3

#### Scenario: Page limit
- **WHEN** `fetch.max_pages` is 400 and wave 4 brings the counted pages to 400
- **THEN** the loop stops after wave 4 with `page limit reached`

#### Scenario: Extraction provider down
- **WHEN** every extraction call of wave 2 fails with a provider error
- **THEN** the loop stops with `extract failed`, `assemble` runs on wave 1's records, and the run succeeds with a warning

#### Scenario: Stopped by the user
- **WHEN** the user answers "No, assemble now" after wave 2
- **THEN** the loop stops with `stopped by user`, the note reads "Stopped by the user after wave 2.", and `assemble` runs

### Requirement: Resume and fork of a catalog run
A catalog run SHALL count its loop stages as finished only after
`catalog.done`. A run resumed before that SHALL reload `nodes.jsonl`, set
every `expanding` node back to `discovered`, keep `extracted` and `failed`
nodes and their records, and continue the loop with the next wave number.
`fork --from expand` SHALL copy every artifact of the parent, accept new
limits (each at least the parent's), set `expanded` false on nodes left
unexpanded only because of the old `max_depth` or `max_nodes` and mark
them `discovered`, and continue the loop; a fork with no limit raised
SHALL fail naming the limits. `fork --from extract` SHALL copy
`structure.json`, `plan.json`, `hits.jsonl`, `pages.jsonl`, `chunks.jsonl`,
and `nodes.jsonl` with every node's status reset to `discovered` and
`expanded` kept, SHALL NOT copy `records.jsonl` or `catalog.json`, and
SHALL run one `extract` pass over every node with its recorded pages,
then `assemble`, with `expand`, `search`, and `fetch` skipped. Any other
`--from` on a catalog run SHALL fail listing `expand` and `extract`.

#### Scenario: Interrupted in wave 3
- **WHEN** a run was interrupted while wave 3 had 12 nodes `expanding` and is resumed
- **THEN** those 12 nodes are `discovered` again, wave 3 runs with them, and the 72 records of waves 1 and 2 are kept

#### Scenario: Expand more
- **WHEN** a finished run with `max_depth` 3 is forked from `expand` with `max_depth` 4
- **THEN** the fork keeps the parent's records, marks the depth-3 non-leaf nodes `discovered`, and runs wave 6 with them

#### Scenario: Re-extract
- **WHEN** a finished run is forked from `extract` with `--use llm=sonnet`
- **THEN** no search or fetch request is made, every node is extracted again from its recorded pages with the `sonnet` entry, and a new `catalog.json` is written

#### Scenario: Fork from fetch
- **WHEN** a catalog run is forked with `--from fetch`
- **THEN** the fork fails listing `expand` and `extract`

### Requirement: Wave pause
After a wave that found at least one new node, when the run's
`questions.rounds` is on and a stop rule does not already hold, the loop
SHALL pause as run-questions "Round pause" defines for catalogs ("Continue
to wave <k+1>?"). "No, assemble now" SHALL stop the loop with `stopped by
user`.

#### Scenario: Continue
- **WHEN** the user answers "Yes" after wave 1
- **THEN** wave 2 runs with the nodes found in wave 1

#### Scenario: No new nodes, no pause
- **WHEN** wave 3 finds no new node
- **THEN** the loop stops with `frontier empty` without pausing
