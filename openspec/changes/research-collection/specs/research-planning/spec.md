# Spec Delta

## Purpose

Turns the user's query into a short list of focused sub-queries, using real
search result titles and snippets and the outlines of attached files, while
keeping fetched page content away from the planner.

## ADDED Requirements

### Requirement: Query identity
The main query SHALL have the query ID `q0`. Sub-queries SHALL have the IDs
`q1`, `q2`, and so on, in the order the planner returned them. A plan SHALL
list the main query first, then the sub-queries.

#### Scenario: IDs in order
- **WHEN** the planner returns the sub-queries "a" and "b" for the query "q"
- **THEN** the plan is `q0` "q", `q1` "a", `q2` "b"

### Requirement: Initial search
Before planning, when web sources are enabled, the system SHALL search once
with the main query. The resulting hits SHALL carry the query ID `q0` and
SHALL count as hits of the main query in the later search results, so the
main query is not searched twice.

#### Scenario: Initial hits reused
- **WHEN** the initial search finds `https://a.example/x` and the sub-query search does not
- **THEN** the merged hits contain `https://a.example/x` with the query IDs `q0`

### Requirement: Planner input
The planner SHALL receive the main query, the title and snippet of each
initial search hit (at most 10, in rank order), and an outline of each
attachment. It SHALL NOT receive fetched page content. The query and
options SHALL be the only values placed into the prompt template; hit
titles, snippets, and outlines SHALL be sent in a separate message,
delimited and marked as data.

#### Scenario: Snippets are data
- **WHEN** a hit snippet contains the text `$query` or "ignore previous instructions"
- **THEN** the snippet appears unchanged inside the delimited data message and the system message contains only the template filled with the query and options

#### Scenario: No page content
- **WHEN** pages have already been fetched for some hits
- **THEN** no fetched page text appears in any message sent to the planner

### Requirement: Attachment outline
The outline of an attachment SHALL contain its title, each heading with its
level, and the first two non-empty lines under each heading, cut to at most
2000 characters per attachment.

#### Scenario: Outline of a short file
- **WHEN** an attachment has the headings "Intro" and "Method", each followed by three lines
- **THEN** its outline lists both headings, each with its first two lines and not the third

### Requirement: Planner output
The planner SHALL return at most `plan.max_sub_queries` sub-queries
(default 3). Sub-queries SHALL be trimmed, empty ones dropped, and
duplicates (ignoring case and surrounding whitespace, including a repeat of
the main query) dropped. When the planner's answer cannot be read, the plan
SHALL contain only the main query and a warning that says why.

#### Scenario: Too many sub-queries
- **WHEN** `plan.max_sub_queries = 3` and the planner returns five sub-queries
- **THEN** the plan keeps the first three

#### Scenario: Duplicate of the main query
- **WHEN** the planner returns the main query again, in a different case
- **THEN** that sub-query is dropped

#### Scenario: Unreadable answer
- **WHEN** the planner's answer contains no list of sub-queries
- **THEN** the plan has only `q0` and one warning

### Requirement: Sources setting
With sources `files`, the system SHALL NOT run the initial search, SHALL NOT
call the planner, and the plan SHALL contain only the main query. With
sources `web`, attachments SHALL be ignored and the planner SHALL receive
no outlines. With sources `both` (the default), the planner SHALL receive
both snippets and outlines.

#### Scenario: Document questions only
- **WHEN** a run uses sources `files`
- **THEN** no search request and no LLM request is made, and the plan is `q0` only
