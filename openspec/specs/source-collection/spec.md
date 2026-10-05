# source-collection Specification

## Purpose

Collects the pages a run reads: web pages found by the sub-queries and the
user's attached files, each fetched or loaded once, with failures and
skipped files reported instead of stopping the run.

## Requirements

### Requirement: Search over queries
The search stage SHALL search every given query, with requests running
concurrently. The text sent to the searcher SHALL be at most 200
characters: a longer query text SHALL be cut at the last whitespace within
that limit (or at 200 characters when there is none), with surrounding
whitespace trimmed. Each query SHALL keep at most `search.max_results` hits
(default 10) after domain filtering, in the order the search provider
returned them, ranked 1 for the first kept hit. Each hit SHALL record its
URL, title, snippet, its best (lowest) search rank, and the IDs of every
query that found it. A failed search for one query SHALL be recorded with
the query ID and the reason, and the other queries SHALL still be searched.
Each new or updated hit SHALL be reported to the stage's item callback. The
plan step's initial search of a short query SHALL follow the same rules.

#### Scenario: Two queries find one page
- **WHEN** `q1` and `q2` both return `https://a.example/x`
- **THEN** the result has one hit for that URL with the query IDs `q1` and `q2`

#### Scenario: One search fails
- **WHEN** the search for `q2` raises an error and `q1` returns hits
- **THEN** the result contains the hits of `q1` and one failure naming `q2` and the error text

#### Scenario: Long query text
- **WHEN** a query's text is 1500 characters of words separated by spaces
- **THEN** the searcher receives at most its first 200 characters, ending at a word boundary, and the query keeps its full text in the plan

#### Scenario: Result cap
- **WHEN** `search.max_results = 5` and the search provider returns 20 results for `q1`
- **THEN** `q1` has 5 hits, ranked 1 to 5 in the provider's order

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
The fetch stage SHALL keep at most `fetch.max_pages` counted pages (thin
pages, below, are not counted). In a multi-round run each round's fetch
uses its round cap in place of `fetch.max_pages` (research-rounds "Fetch
and pairing across rounds"); below, "the cap" means the one that fetch
uses.
Unique hits SHALL be queued round-robin across queries in query order (`q0`
first), taking each query's hits in rank order. A hit found by several
queries SHALL be queued once, at its earliest turn. Fetches SHALL start in
queue order, within the `fetch.concurrency` limit. A failed or empty fetch
SHALL NOT count toward the cap: the next queued hit is fetched in its place.

A thin page is a fetched web page whose text has fewer than
`chunk.min_chars` characters (default 500), measured as the page's
character count (the `chars` of `page.fetched`). Attached files are never
thin.
A thin page SHALL be kept and recorded like any other page, but SHALL NOT
count toward the cap, so the next queued hit is fetched in its place. At
most as many thin pages as the cap SHALL be exempt in one fetch; thin
pages beyond that count toward the cap. With `chunk.min_chars =
0` no page is thin.

No new fetch SHALL start once the counted pages plus the fetches in flight
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

#### Scenario: Thin page replaced
- **WHEN** `fetch.max_pages = 2`, `fetch.concurrency = 1`, `chunk.min_chars = 500`, and the queue is X, Y, Z with X returning 94 characters
- **THEN** X, Y, and Z are all kept as pages, X is thin, and no hit is reported as not fetched

#### Scenario: Thin exemption bounded
- **WHEN** `fetch.max_pages = 2`, `fetch.concurrency = 1`, and every queued hit returns a thin page
- **THEN** the stage keeps 4 pages (2 exempt, 2 counted) and reports the rest as not fetched

#### Scenario: Thin exemption uses the round cap
- **WHEN** a 2-round run has `fetch.max_pages = 15`, round 1's cap is 8, and every round-1 hit returns a thin page
- **THEN** round 1 keeps 16 pages (8 exempt, 8 counted)

### Requirement: Domain filter
The search stage SHALL drop every hit whose host is blocked, and, when the
run's allow list is not empty, every hit whose host is not allowed. The
run's lists are `search.allow_domains` and `search.block_domains` after
global settings and run overrides (http-api "Run request precedence"). A
host matches a domain entry when it equals the entry or ends with `.`
followed by the entry, compared without case, port, or a trailing dot. A
host that matches the block list SHALL be dropped even when it also matches
the allow list. Hits SHALL be filtered before they are merged, counted
against `search.max_results`, or reported to the item callback. The stage
SHALL report how many distinct normalised URLs it dropped. Attachments
SHALL never be filtered.

#### Scenario: Allowed suffix
- **WHEN** `search.allow_domains = ["gob.pe"]` and a query finds `https://www.gob.pe/a`, `https://cej.pj.gob.pe/b`, `https://notgob.pe/c`, and `https://infobae.com/d`
- **THEN** the hits are `https://www.gob.pe/a` and `https://cej.pj.gob.pe/b`, and 2 hits are reported as filtered

#### Scenario: Block wins
- **WHEN** `search.allow_domains = ["gob.pe"]`, `search.block_domains = ["facilito.gob.pe"]`, and a query finds `https://facilito.gob.pe/x` and `https://www.gob.pe/y`
- **THEN** only `https://www.gob.pe/y` is kept

#### Scenario: Block list only
- **WHEN** `search.allow_domains = []`, `search.block_domains = ["facebook.com"]`, and a query finds `https://m.facebook.com/p` and `https://a.example/x`
- **THEN** only `https://a.example/x` is kept

#### Scenario: No filter
- **WHEN** both lists are empty
- **THEN** no hit is dropped and 0 hits are reported as filtered

#### Scenario: Same URL dropped twice
- **WHEN** `search.block_domains = ["x.com"]` and `q1` and `q2` both find `https://x.com/a`
- **THEN** 1 hit is reported as filtered

#### Scenario: Initial search filtered
- **WHEN** the query is "SINOE casilla electrónica" (a short query, so the plan step searches it first) and `search.allow_domains = ["gob.pe"]`
- **THEN** `initial.jsonl` holds only `gob.pe` hosts, the planner sees only their snippets, and the plan stage reports the dropped count

#### Scenario: Attachments untouched
- **WHEN** `search.allow_domains = ["gob.pe"]` and the run has the attachment `notes.md`
- **THEN** `notes.md` is loaded, chunked, and scored as without a filter

### Requirement: Extra result pages while filtering
While either domain list is not empty, the search stage SHALL read the
next result page of a query when that query has fewer than
`search.max_results` kept hits, the last page returned at least one
result, and fewer than `search.filter_pages` pages (default 3) were read.
Without a domain filter, the stage SHALL read only the first page. A
failure on a later page SHALL keep the hits of the earlier pages and SHALL
be recorded as that query's failure.

#### Scenario: Second page fills the query
- **WHEN** `search.allow_domains = ["gob.pe"]`, `search.max_results = 5`, page 1 of `q1` has 2 allowed hits, and page 2 has 4 allowed hits
- **THEN** `q1` has 5 hits and page 3 is not read

#### Scenario: Page limit
- **WHEN** `search.filter_pages = 2` and pages 1 and 2 of `q1` have no allowed hit
- **THEN** `q1` has no hits and page 3 is not read

#### Scenario: Empty page stops
- **WHEN** a filter is set and page 2 of `q1` returns no results
- **THEN** page 3 is not read

#### Scenario: No filter reads one page
- **WHEN** both domain lists are empty and page 1 of `q1` returns 3 results with `search.max_results = 10`
- **THEN** `q1` has 3 hits and page 2 is not read

#### Scenario: Later page fails
- **WHEN** a filter is set, page 1 of `q1` has 2 allowed hits, and page 2 raises an error
- **THEN** `q1` keeps its 2 hits and the result has one failure naming `q1`
