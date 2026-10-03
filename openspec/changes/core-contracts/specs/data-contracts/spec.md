# Spec Delta

## Purpose

Defines the data that flows between pipeline stages, its stable identities,
and a published JSON Schema, so stages, the run store, the server, and the
frontend agree on one shape.

## ADDED Requirements

### Requirement: Contract types
The system SHALL define these data types: run request, query, search hit,
source, page, chunk, score, selected context, report, and writing options.
Each type SHALL serialise to JSON and parse back to an equal value.

#### Scenario: Round trip
- **WHEN** any contract value is serialised to JSON and parsed again
- **THEN** the parsed value equals the original

#### Scenario: Unknown fields rejected
- **WHEN** JSON for a contract type contains a field the type does not define
- **THEN** parsing fails with an error that names the field

### Requirement: Source identity
Every source SHALL have a kind (`web` or `file`), a URI, a title, and a
`source_id`. For web sources the `source_id` SHALL be derived from the
normalised URL; for file sources from the file content SHA-256. The same
input SHALL always produce the same `source_id`.

#### Scenario: Normalised URLs share an ID
- **WHEN** two web sources have the URLs `https://Example.com/a/?utm_source=x#top` and `https://example.com/a`
- **THEN** both have the same `source_id`

#### Scenario: Same file content
- **WHEN** two attachments at different paths have identical content
- **THEN** both have the same `source_id`

### Requirement: URL normalisation
URL normalisation SHALL lowercase the scheme and host, remove the fragment,
remove a trailing slash from the path, remove tracking query parameters
(`utm_*`, `fbclid`, `gclid`), and sort the remaining query parameters.

#### Scenario: Query parameter order
- **WHEN** two URLs differ only in the order of their query parameters
- **THEN** they normalise to the same URL

#### Scenario: Meaningful parameters kept
- **WHEN** a URL has the query parameter `id=42`
- **THEN** the normalised URL keeps `id=42`

### Requirement: Chunk identity
Every chunk SHALL have a `chunk_id` derived from its `source_id`, its
position in the source, and its text, and SHALL carry its heading path.
The same input SHALL always produce the same `chunk_id`.

#### Scenario: Deterministic chunk ID
- **WHEN** the same page is chunked twice with the same settings
- **THEN** each chunk gets the same `chunk_id` both times

### Requirement: Scores are pairs
A score SHALL record a query ID, a chunk ID, a numeric value, and the name
of the scorer that produced it.

#### Scenario: Same chunk, two queries
- **WHEN** one chunk is scored against two queries
- **THEN** two scores exist, one per query, each naming the scorer

### Requirement: Writing options
Writing options SHALL have the fields `tone`, `tone_instructions`, `words`,
`language`, `citation_marker`, and `reference_style`, with defaults
`objective`, empty, 1200, `english`, `numeric`, and `APA`. `words` SHALL be a
positive integer. `citation_marker` SHALL be one of `numeric`,
`superscript`, or `author-year`. `tone` and `reference_style` SHALL accept
any name; whether the name exists is checked where tones and reference
formats are loaded, not in the contract.

#### Scenario: Defaults
- **WHEN** writing options are created with no fields
- **THEN** they have tone `objective`, words 1200, language `english`, citation marker `numeric`, and reference style `APA`

#### Scenario: Invalid marker
- **WHEN** writing options are created with `citation_marker = "footnote"`
- **THEN** validation fails and names `citation_marker` and the allowed values

#### Scenario: Invalid length
- **WHEN** writing options are created with `words = 0`
- **THEN** validation fails and names `words`

### Requirement: Published JSON Schema
`wosarcher schema` SHALL print one JSON Schema document that covers every contract
type, so other programs (the frontend) can generate types from it. The
output SHALL be identical for identical code.

#### Scenario: Stable output
- **WHEN** `wosarcher schema` runs twice on the same version
- **THEN** both outputs are byte-identical
