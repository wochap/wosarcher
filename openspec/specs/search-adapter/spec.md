# search-adapter Specification

## Purpose

Finds web pages for a query through a SearXNG instance (self-hosted or any
URL that allows JSON output), returning ranked hits for the fetch stage.

## Requirements

### Requirement: SearXNG JSON search
The search adapter SHALL send `GET <base_url>/search` with the query text,
`format=json`, and `pageno=1`, and SHALL turn each result that has a URL
into a hit with the result's URL, title, snippet (the result's `content`),
its rank (1 for the first kept result), and the ID of the query that found
it. Results without a URL SHALL be skipped. When two results normalise to
the same URL, only the first SHALL be kept. A response with no results
SHALL give an empty list, not an error.

#### Scenario: Results become hits
- **WHEN** SearXNG answers with three results for query `q1`
- **THEN** three hits are returned in SearXNG's order, ranked 1 to 3, each carrying query ID `q1`

#### Scenario: Duplicate URLs
- **WHEN** SearXNG returns `https://a.com/x` and `https://A.com/x/#top`
- **THEN** one hit is returned, from the first result

#### Scenario: No results
- **WHEN** SearXNG answers with an empty `results` list
- **THEN** the adapter returns an empty list

### Requirement: Search settings
The adapter SHALL return at most `search.max_results` hits (default 10).
When `search.language` is set it SHALL be sent as `language`; when
`search.time_range` is set (`day`, `week`, `month`, or `year`) it SHALL be
sent as `time_range`. Unset values SHALL NOT be sent. Any other
`time_range` value SHALL be rejected when the configuration is resolved.

#### Scenario: Result cap
- **WHEN** `search.max_results = 5` and SearXNG returns 20 results
- **THEN** 5 hits are returned

#### Scenario: Language and time range sent
- **WHEN** `search.language = "de"` and `search.time_range = "month"`
- **THEN** the request carries `language=de` and `time_range=month`

#### Scenario: Defaults omit parameters
- **WHEN** neither `search.language` nor `search.time_range` is set
- **THEN** the request has no `language` or `time_range` parameter

### Requirement: JSON format disabled
When SearXNG answers 403, the error SHALL say that the instance must allow
the `json` format (`search.formats` in SearXNG's settings).

#### Scenario: Forbidden
- **WHEN** SearXNG answers 403
- **THEN** the search fails with an error that mentions enabling the `json` format

### Requirement: Search usage
Each search request SHALL be recorded in the usage ledger for the stage
that made it, with no tokens.

#### Scenario: Request counted
- **WHEN** two searches run in the search stage
- **THEN** the ledger shows two requests for SearXNG in that stage
