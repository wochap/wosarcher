# Spec Delta

## MODIFIED Requirements

### Requirement: Reference list
When any passage is cited, the rendered report SHALL end with a
`## References` section listing each cited source once, in order of first
citation, formatted in the `reference_style` (`APA`, `MLA`, `Chicago`, or
`IEEE`, matched without regard to case). A reference entry SHALL never
contain two periods in a row, including when the year is `n.d.`. Under
each source, the cited passages SHALL be listed as `[n]` followed by the
pdf-ingest page ID (as `p. <id>`, with block IDs in parentheses) or, when
there is none, the heading path. An unknown reference style SHALL fail
before the LLM is called, with an error that lists the known styles.

#### Scenario: APA web source
- **WHEN** the style is `APA` and passage 2 from "Draft models" by "Lee" (2024) at `https://example.org/d` under "Results" is cited
- **THEN** the reference list contains `Lee (2024). *Draft models*. example.org. https://example.org/d` with `[2] Results` under it

#### Scenario: IEEE numbering
- **WHEN** the style is `IEEE` and two sources are cited
- **THEN** the entries start with `[1]` and `[2]` in order of first citation

#### Scenario: pdf-ingest file
- **WHEN** a cited passage 4 comes from an attached file with page ID `12` and block ID `p12-b3`
- **THEN** that source's entry lists `[4] p. 12 (p12-b3)`

#### Scenario: Undated file source
- **WHEN** the style is `MLA`, `Chicago`, or `IEEE` and a cited file source `paper.pdf` titled "Paper" has no date
- **THEN** its entry ends with `n.d.` and contains no `..` (MLA `"Paper." *paper.pdf*, n.d.`)

#### Scenario: Unknown style
- **WHEN** the reference style is `Harvard`
- **THEN** the stage fails without an LLM call and the error lists APA, MLA, Chicago, and IEEE
