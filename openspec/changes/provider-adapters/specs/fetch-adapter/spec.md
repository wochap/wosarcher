# Spec Delta

## Purpose

Fetches web pages and PDFs at URLs as markdown through Firecrawl
(self-hosted or the cloud API), so later stages work on clean text.

## ADDED Requirements

### Requirement: Firecrawl scrape
The fetch adapter SHALL send `POST <base_url>/scrape` with the URL,
`formats: ["markdown"]`, `onlyMainContent` from `fetch.only_main_content`
(default true), and `timeout` in milliseconds from `fetch.page_timeout`
(default 45 seconds). It SHALL return a page with a web source for the
requested URL, the page title (the URL when the title is missing), and the
markdown. `base_url` selects the deployment, for example
`https://api.firecrawl.dev/v1` or a self-hosted `http://host:3002/v1`; the
API key is sent only when configured.

#### Scenario: Page fetched
- **WHEN** Firecrawl answers `success: true` with markdown and title `Battery recycling`
- **THEN** the page has that title, that markdown, and a source for the requested URL

#### Scenario: Self-hosted without key
- **WHEN** `fetch.api_key` is unset
- **THEN** the request has no `Authorization` header

#### Scenario: PDF at a URL
- **WHEN** the URL points to a PDF and Firecrawl answers with its markdown
- **THEN** the page holds that markdown like any other page

### Requirement: Page timeout below request timeout
`fetch.page_timeout` SHALL be lower than `fetch.timeout`, so Firecrawl
reports a slow page before the HTTP request itself times out. A
configuration that breaks this SHALL be rejected when it is resolved,
naming both fields.

#### Scenario: Invalid timeouts
- **WHEN** a profile sets `fetch.page_timeout = 60` and `fetch.timeout = 30`
- **THEN** resolution fails naming `fetch.page_timeout` and `fetch.timeout`

### Requirement: Size cap
Page markdown SHALL be cut to at most `fetch.max_chars` characters
(default 50000).

#### Scenario: Long page
- **WHEN** Firecrawl returns 80000 characters and `fetch.max_chars = 50000`
- **THEN** the page text has 50000 characters

### Requirement: Failed pages
The adapter SHALL fail the fetch of that URL, with an error naming the URL
and the reason, when Firecrawl answers `success: false`, when the target
answered with an HTTP status of 400 or higher (`metadata.statusCode`), or
when the markdown is empty or only whitespace.

#### Scenario: Target not found
- **WHEN** Firecrawl answers `success: true` with `metadata.statusCode = 404`
- **THEN** the fetch fails with an error naming the URL and status 404

#### Scenario: Empty page
- **WHEN** Firecrawl returns markdown that is only whitespace
- **THEN** the fetch fails with an error naming the URL and saying the page is empty

### Requirement: Fetch usage
Each scrape SHALL be recorded in the usage ledger with units equal to
`metadata.creditsUsed` when Firecrawl reports it, otherwise 1.

#### Scenario: Credits recorded
- **WHEN** a scrape reports `creditsUsed: 1` and another reports none
- **THEN** the ledger shows 2 requests and 2 units for Firecrawl in the fetch stage
