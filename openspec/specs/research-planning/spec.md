# research-planning Specification

## Purpose

Turns the user's query into a short list of focused sub-queries, using real
search result titles and snippets and the outlines of attached files, while
keeping fetched page content away from the planner.

## Requirements

### Requirement: Query identity
The main query SHALL have the query ID `q0`. Its text SHALL be the topic
line: the planner's short statement of what to search for and rank
against, or the fallback topic (see Requirement: Topic fallback). The
user's query SHALL NOT be the text of `q0` when the planner gives a usable
topic; it SHALL stay on the run request, where the planner, the gap step,
and the writer read it. Sub-queries SHALL have the IDs `q1`, `q2`, and so
on, in the order the planner returned them. A plan SHALL list the main
query first, then the sub-queries.

#### Scenario: IDs in order
- **WHEN** the planner returns the topic "t" and the sub-queries "a" and "b" for the query "q"
- **THEN** the plan is `q0` "t", `q1` "a", `q2` "b"

#### Scenario: Brief stays on the request
- **WHEN** the user's query is a 4000-character brief and the planner returns the topic "alertas de notificaciones legales para personas naturales en Perú"
- **THEN** `q0` has that topic as its text and the writer's task contains the full brief

### Requirement: Initial search
Before planning, when web sources are enabled and the user's query is at
most 200 characters after trimming whitespace, the system SHALL search once
with the user's query. The resulting hits SHALL carry the query ID `q0` and
SHALL count as hits of the main query in the later search results, so `q0`
is not searched again in round 1. When the query is longer than 200
characters, the system SHALL NOT search before planning, the run's
`initial.jsonl` SHALL be empty, and the search stage SHALL search `q0` (the
topic line) with the sub-queries.

#### Scenario: Initial hits reused
- **WHEN** the query is "what is BM25", the initial search finds `https://a.example/x`, and the sub-query search does not
- **THEN** the merged hits contain `https://a.example/x` with the query IDs `q0`, and the search stage does not search `q0`

#### Scenario: Long brief skips the initial search
- **WHEN** a run with sources `web` has a 4000-character query
- **THEN** no search request is made before the planner is called, `initial.jsonl` is empty, and the search stage searches `q0` with the sub-queries

#### Scenario: Exactly at the limit
- **WHEN** the query is 200 characters after trimming
- **THEN** the initial search runs with that query

### Requirement: Planner input
The planner SHALL receive the user's query, the title and snippet of each
initial search hit (at most 10, in rank order) when the initial search ran,
and an outline of each attachment. It SHALL NOT receive fetched page
content. The query and options SHALL be the only values placed into the
prompt template; hit titles, snippets, and outlines SHALL be sent in a
separate message, delimited and marked as data.

#### Scenario: Snippets are data
- **WHEN** a hit snippet contains the text `$query` or "ignore previous instructions"
- **THEN** the snippet appears unchanged inside the delimited data message and the system message contains only the template filled with the query and options

#### Scenario: No page content
- **WHEN** pages have already been fetched for some hits
- **THEN** no fetched page text appears in any message sent to the planner

#### Scenario: Long query has no snippets
- **WHEN** the query is longer than 200 characters and the run has no attachments
- **THEN** the planner's data message holds no hit titles or snippets

### Requirement: Attachment outline
The outline of an attachment SHALL contain its title, each heading with its
level, and the first two non-empty lines under each heading, cut to at most
2000 characters per attachment.

#### Scenario: Outline of a short file
- **WHEN** an attachment has the headings "Intro" and "Method", each followed by three lines
- **THEN** its outline lists both headings, each with its first two lines and not the third

### Requirement: Planner output
The planner SHALL return a topic line and at most `plan.max_sub_queries`
sub-queries (default 3). The planner SHALL be asked for one sub-query per
distinct topic of the user's query, up to that limit, and fewer when the
query is narrow. The topic and the sub-queries SHALL be trimmed. A topic
that is empty or longer than 200 characters SHALL be treated as missing.
Empty sub-queries SHALL be dropped, and duplicates (ignoring case and
surrounding whitespace, including a repeat of the topic or of the user's
query) SHALL be dropped. When the planner's answer cannot be read, the plan
SHALL contain only the main query with the fallback topic and a warning
that says why. When the answer has sub-queries but no usable topic, the
plan SHALL keep the sub-queries, use the fallback topic, and add a warning.

In the same call the planner SHALL be asked for the question parts: the
distinct things the user's query asks for, as short phrases, at most 12.
The answer's `parts` field SHALL be a list of strings; parts SHALL be
trimmed, empty ones and duplicates (ignoring case and surrounding
whitespace) dropped, and at most the first 12 kept. The plan SHALL save
them as `parts` in `plan.json`, in the planner's order. When the answer has
a readable query list but `parts` is missing, is not a list of strings, or
keeps no part, the plan SHALL have an empty parts list and one warning
that says so; the run SHALL NOT fail. A bare-list answer has no parts.
When the planner does not run (sources `files`, or `plan.max_sub_queries =
0`) or its answer cannot be read, the plan SHALL have an empty parts list
and no parts warning.

#### Scenario: Too many sub-queries
- **WHEN** `plan.max_sub_queries = 3` and the planner returns five sub-queries
- **THEN** the plan keeps the first three

#### Scenario: Duplicate of the main query
- **WHEN** the planner returns the topic or the user's query again as a sub-query, in a different case
- **THEN** that sub-query is dropped

#### Scenario: Unreadable answer
- **WHEN** the planner's answer contains no list of sub-queries
- **THEN** the plan has only `q0` with the fallback topic, and one warning

#### Scenario: Sub-queries without a topic
- **WHEN** the planner answers with a bare list of two sub-queries
- **THEN** the plan has `q0` with the fallback topic, `q1`, `q2`, and one warning

#### Scenario: Parts saved
- **WHEN** the planner answers `{"topic": "t", "queries": ["a"], "parts": ["cost", " Cost ", "setup", ""]}`
- **THEN** `plan.json` has `parts` = `["cost", "setup"]` and no parts warning

#### Scenario: Too many parts
- **WHEN** the planner answers 15 distinct parts
- **THEN** the plan keeps the first 12

#### Scenario: Parts missing
- **WHEN** the planner answers `{"topic": "t", "queries": ["a", "b"]}`
- **THEN** the plan has `q0` "t", `q1`, `q2`, an empty parts list, and one warning about the parts

#### Scenario: Malformed parts
- **WHEN** the planner answers `{"topic": "t", "queries": ["a"], "parts": "cost and setup"}`
- **THEN** the plan keeps its queries, has an empty parts list, and one warning about the parts

#### Scenario: No planner, no parts
- **WHEN** a run uses sources `files`
- **THEN** the plan has an empty parts list and no warning

### Requirement: Sources setting
With sources `files`, the system SHALL NOT run the initial search, SHALL NOT
call the planner, and the plan SHALL contain only the main query, with the
fallback topic. With sources `web`, attachments SHALL be ignored and the
planner SHALL receive no outlines. With sources `both` (the default), the
planner SHALL receive the outlines, and the snippets when the initial search
ran.

#### Scenario: Document questions only
- **WHEN** a run uses sources `files`
- **THEN** no search request and no LLM request is made, and the plan is `q0` only

### Requirement: Topic fallback
When the planner does not run (sources `files`, or `plan.max_sub_queries =
0`) or gives no usable topic, the text of `q0` SHALL be the user's query.
With sources `files` the whole query SHALL be used. Otherwise it SHALL be
cut to at most 200 characters at the last whitespace within that limit
(or at 200 characters when there is none), with surrounding whitespace
trimmed.

#### Scenario: Long query without a planner
- **WHEN** `plan.max_sub_queries = 0` and the user's query is 1500 characters with spaces
- **THEN** `q0` holds the query's first words, at most 200 characters, ending at a word boundary

#### Scenario: Short query without a planner
- **WHEN** `plan.max_sub_queries = 0` and the user's query is "what is BM25"
- **THEN** `q0` is "what is BM25"
