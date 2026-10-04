# source-collection Specification

## Purpose

Collects the pages a run reads: web pages found by the sub-queries and the
user's attached files, each fetched or loaded once, with failures and
skipped files reported instead of stopping the run.

## Requirements

### Requirement: Search over queries
The search stage SHALL search every given query, with requests running
concurrently. Each hit SHALL record its URL, title, snippet, its best
(lowest) search rank, and the IDs of every query that found it. A failed
search for one query SHALL be recorded with the query ID and the reason,
and the other queries SHALL still be searched. Each new or updated hit
SHALL be reported to the stage's item callback.

#### Scenario: Two queries find one page
- **WHEN** `q1` and `q2` both return `https://a.example/x`
- **THEN** the result has one hit for that URL with the query IDs `q1` and `q2`

#### Scenario: One search fails
- **WHEN** the search for `q2` raises an error and `q1` returns hits
- **THEN** the result contains the hits of `q1` and one failure naming `q2` and the error text

### Requirement: URL dedupe
Hits SHALL be merged by normalised URL (core-contracts URL normalisation),
across the initial search and every sub-query. Each normalised URL SHALL be
fetched at most once per run.

#### Scenario: Tracking parameters
- **WHEN** one query finds `https://a.example/x?utm_source=s` and another finds `https://A.example/x/`
- **THEN** there is one hit and the fetcher is called once for it

### Requirement: Fetch with failures
The fetch stage SHALL fetch hits with at most `fetch.concurrency` requests in
flight (default 6). A page that fails to fetch or comes back empty SHALL be
recorded as a failure with its URL and reason, and the stage SHALL continue
with the other pages. Each fetched page and each failure SHALL be reported to
the stage's item callback. Each fetched page SHALL carry the query IDs and
best rank of its hit.

#### Scenario: One page fails
- **WHEN** three hits are fetched and the second raises an error
- **THEN** the result has two pages and one failure with the second URL and the error text

#### Scenario: Empty page
- **WHEN** the fetcher returns a page with no text
- **THEN** it is recorded as a failure with the reason "empty content"

#### Scenario: Concurrency limit
- **WHEN** `fetch.concurrency = 2` and ten hits are fetched
- **THEN** no more than two fetches are in flight at any time

### Requirement: Page cap
A fetched web page longer than `fetch.max_chars` characters (default 50000)
SHALL be cut to that length by the fetch adapter and marked as truncated.
The fetch stage SHALL NOT cut page text again.

#### Scenario: Long page
- **WHEN** Firecrawl returns 80000 characters and `fetch.max_chars = 50000`
- **THEN** the page text has 50000 characters and is marked truncated

### Requirement: Attachment paths
Attachments SHALL be given as files, directories, or glob patterns.
Directories SHALL be read recursively in sorted path order, skipping hidden
files and directories. Only `.md` and `.txt` files SHALL be loaded; any
other file SHALL be skipped with a warning that names it. A file larger
than `attach.max_bytes` (default 5000000) SHALL be skipped with a warning.
A path or pattern that matches no file SHALL fail before any stage runs,
with an error that names it.

#### Scenario: Mixed directory
- **WHEN** a directory holds `a.md`, `b.txt`, and `c.pdf`
- **THEN** `a.md` and `b.txt` are loaded and `c.pdf` is skipped with a warning naming it

#### Scenario: Oversized file
- **WHEN** an attached `.md` file is larger than `attach.max_bytes`
- **THEN** it is skipped with a warning that names the file and the limit

#### Scenario: Nothing matches
- **WHEN** `--attach ./missing/*.md` matches no file
- **THEN** the run fails before searching, and the error names the pattern

### Requirement: Attachment loading
Attachment bytes SHALL be decoded as UTF-8, with invalid bytes replaced.
Each attachment SHALL become a file page whose `source_id` comes from its
content. Attachments with identical content SHALL be loaded once, and the
later ones reported as duplicates. The page title SHALL be the first
level-one heading, or the file name when there is none.

#### Scenario: Invalid bytes
- **WHEN** an attachment contains a byte sequence that is not valid UTF-8
- **THEN** it loads, and the invalid bytes appear as the replacement character

#### Scenario: Same content twice
- **WHEN** `a.md` and `copy/a.md` have the same bytes
- **THEN** one page is loaded and the second file is reported as a duplicate

### Requirement: pdf-ingest detection
An attachment that contains at least one `<!-- page: … -->` comment SHALL be
marked as pdf-ingest markdown, so chunking keeps its page and block IDs.

#### Scenario: Converted PDF
- **WHEN** an attachment contains `<!-- page: 3 -->` and `<!-- a: p3-b2 -->`
- **THEN** its page is marked as pdf-ingest markdown

### Requirement: Fetch page cap and order
The fetch stage SHALL fetch at most `fetch.max_pages` pages successfully.
Unique hits SHALL be queued round-robin across queries in query order (`q0`
first), taking each query's hits in rank order. A hit found by several
queries SHALL be queued once, at its earliest turn. Fetches SHALL start in
queue order, within the `fetch.concurrency` limit. A failed or empty fetch
SHALL NOT count toward the cap: the next queued hit is fetched in its place.
No new fetch SHALL start once the pages fetched plus the fetches in flight
reach the cap. Queued hits that were never fetched SHALL NOT be recorded as
failures. The stage SHALL report how many there were.

#### Scenario: Fair order
- **WHEN** `fetch.max_pages = 4`, `fetch.concurrency = 1`, `q1` found A1, A2, A3, and `q2` found B1, B2, B3
- **THEN** the pages fetched are A1, B1, A2, B2 and 2 hits are reported as not fetched

#### Scenario: Failure replaced
- **WHEN** `fetch.max_pages = 2`, `fetch.concurrency = 1`, and the queue is X, Y, Z with X failing
- **THEN** Y and Z are fetched, X is a failure, and no hit is reported as not fetched

#### Scenario: Under the cap
- **WHEN** 10 unique hits are found and `fetch.max_pages = 40`
- **THEN** all 10 are fetched
