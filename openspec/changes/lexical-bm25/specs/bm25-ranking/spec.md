# Spec Delta

## Purpose

Ranks a list of texts for one query by keyword overlap (BM25), locally and
deterministically, so wosarcher can score and prefilter passages without
any model or API.

## ADDED Requirements

### Requirement: Tokenization
Text SHALL be split into Unicode word tokens (letters, digits, and
underscore, in any script) and lowercased. Tokens of one character and
English stopwords SHALL be removed. The stopword check SHALL happen before
stemming. Tokenizing the same text SHALL always give the same tokens in
text order.

#### Scenario: Words and case
- **WHEN** the text `The Battery-Life of EVs in 2024` is tokenized
- **THEN** the tokens are `battery`, `life`, `evs`, `2024`

#### Scenario: Non-Latin scripts kept
- **WHEN** the text `café naïve 東京` is tokenized
- **THEN** the tokens are `café`, `naïve`, `東京`

#### Scenario: Only stopwords
- **WHEN** the text `what is the` is tokenized
- **THEN** the result is empty

### Requirement: Light plural stemming
Tokens longer than four characters SHALL be reduced from plural to singular
with these rules, applied in order, first match wins: a token ending in
`ss` is kept; `ies` becomes `y`; `sses`, `xes`, `zes`, `ches`, and `shes`
lose the final `es`; any other final `s` is removed. Tokens of four
characters or fewer SHALL be kept as they are.

#### Scenario: Plural forms match their singular
- **WHEN** the tokens `batteries`, `costs`, `boxes`, and `churches` are stemmed
- **THEN** they become `battery`, `cost`, `box`, and `church`

#### Scenario: Words that are not plurals
- **WHEN** the tokens `class`, `glass`, `bus`, and `news` are stemmed
- **THEN** all four are unchanged

### Requirement: BM25 scores
For a query and a list of texts, the system SHALL return one non-negative
score per text, in input order, using BM25 with k1 = 1.5 and b = 0.75.
Document frequency, IDF, and average text length SHALL be computed over
the given texts only. IDF SHALL be `ln((N - n + 0.5) / (n + 0.5) + 1)`,
where N is the number of texts and n the number containing the term, so it
is always positive. Each distinct query term SHALL count once, however
often it appears in the query. A text with no query term SHALL score 0.
An empty list of texts SHALL give an empty list of scores.

#### Scenario: Matching text scores higher
- **WHEN** the query is `battery recycling` and the texts are `Battery recycling plants recover lithium.` and `The weather was mild.`
- **THEN** the first score is greater than 0 and the second score is 0

#### Scenario: Rarer terms weigh more
- **WHEN** the query is `solar cost` and the texts are `solar panel`, `cost panel`, and `cost model`
- **THEN** the text `solar panel` scores higher than the text `cost panel`

#### Scenario: Repeated query terms
- **WHEN** the query `cost cost cost` and the query `cost` are scored against the same texts
- **THEN** both give the same scores

#### Scenario: Deterministic
- **WHEN** the same query and texts are scored twice
- **THEN** both results are identical

### Requirement: Ranking with a relative threshold
Ranking SHALL return the positions of the texts to keep, best score first,
ties ordered by input position. A text SHALL be kept only when its score
is at least `relative_threshold` times the best score for the query
(default 0.5) and greater than 0. At most `max_results` positions SHALL be
returned (default 25). `relative_threshold` SHALL be between 0 and 1, and
`max_results` SHALL be at least 1; other values SHALL be rejected with an
error that names the argument.

#### Scenario: Weak matches dropped
- **WHEN** three texts score 4.0, 2.5, and 1.0 with the default threshold
- **THEN** the positions of the texts scoring 4.0 and 2.5 are returned, in that order

#### Scenario: Ties keep input order
- **WHEN** the texts at positions 3 and 1 have the same best score
- **THEN** position 1 comes before position 3

#### Scenario: Result cap
- **WHEN** 40 texts all score the same and `max_results` is 25
- **THEN** positions 0 to 24 are returned

#### Scenario: Invalid threshold
- **WHEN** ranking is called with `relative_threshold = 1.5`
- **THEN** it fails with an error that names `relative_threshold`

### Requirement: No-match fallback
When no text contains any query term (every score is 0), or the query has
no tokens after stopword removal, ranking SHALL return the first
`max_results` positions in input order, so callers that pass texts in
search-rank and page order get the opening texts of the best pages. An
empty list of texts SHALL give an empty result.

#### Scenario: Nothing matches
- **WHEN** the query is `quantum entanglement` and none of 30 texts contains either term, with `max_results = 5`
- **THEN** positions 0 to 4 are returned

#### Scenario: Stopword-only query
- **WHEN** the query is `what is it` and there are 3 texts
- **THEN** positions 0, 1, and 2 are returned

#### Scenario: No texts
- **WHEN** ranking is called with an empty list of texts
- **THEN** the result is empty

### Requirement: Pure and local
BM25 ranking SHALL use no network, no files, no model, and no state kept
between calls. Its result SHALL depend only on its arguments.

#### Scenario: Works offline
- **WHEN** ranking runs on a machine with no network and no configured providers
- **THEN** it returns the same result as on any other machine
