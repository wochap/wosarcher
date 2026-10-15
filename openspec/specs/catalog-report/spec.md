# catalog-report Specification

## Purpose

Lets a catalog run return a written report as well as, or instead of, its
record table: the structure's `output` option, the `write` stage that turns
assembled records into cited passages for the research writer, and the
report's place in the run result and export.

## Requirements

### Requirement: Output option
A structure SHALL have `output`: `table` (default), `report`, or `both`.
With `table` the run SHALL end at `assemble`. With `report` or `both` the
run SHALL write a report after `assemble` (Requirement: Catalog write
stage). The run's writing options SHALL apply only when `output` is not
`table`.

#### Scenario: Table only
- **WHEN** a catalog run has `output` `table`
- **THEN** `assemble` is the last stage, `write` is reported skipped, and no `report.md` is written

#### Scenario: Report wanted
- **WHEN** a catalog run has `output` `both` and writing options tone `objective` and 800 words
- **THEN** `write` runs after `assemble` and writes `report.md` and `report.json` with those options

### Requirement: Catalog write stage
When `output` is `report` or `both`, the runner SHALL build a context from
`catalog.json` after `assemble` and call the write stage as for a research
run. The context SHALL hold one passage per assembled record, in discovery
order, numbered from 1, whose text is the name field's value, then the
type on its own line, then one `<field>: <value>` line per other non-null
field in structure order; whose heading path is the type and the parent
record's name (or the type alone for a seed); and whose source is the
record's first page (its title and URL), or a source titled with the
record's name and without URL when it has none. Each passage SHALL carry
the record ID. Passages SHALL be added while they fit the context budget
of context-selection "Token budget"; `context.json` SHALL be written with
the passages used. The writing task SHALL be the brief followed by the
line "The catalog has <N> records; the passages hold the first <M>." when
M is below N, and SHALL go through the task template as the query does.
Record text SHALL be placed only in the data block. Citations, the
reference list, streaming, continuation, and `report.json` SHALL behave as
report-writing defines. `report.json` SHALL carry `records` true.

#### Scenario: Record passage
- **WHEN** record `sunat` (type `public_body`, parent MEF, fields `acronym` "SUNAT" and `website` "https://www.sunat.gob.pe", first page "SUNAT · gob.pe" at `https://www.gob.pe/sunat`) is the fourth record
- **THEN** passage 4 reads "Superintendencia Nacional de Aduanas y de Administración Tributaria\npublic_body\nacronym: SUNAT\nwebsite: https://www.sunat.gob.pe", its heading path is `["public_body", "Ministerio de Economía y Finanzas"]`, and its source is "SUNAT · gob.pe" at that URL

#### Scenario: Budget cut
- **WHEN** a catalog has 1,400 records and the first 310 fill the budget
- **THEN** the context holds passages 1 to 310 and the task ends with "The catalog has 1400 records; the passages hold the first 310."

#### Scenario: Record text is data
- **WHEN** a record's description contains "Ignore all previous instructions"
- **THEN** the text appears only inside the data block of the writer's user message

#### Scenario: Citation to a record
- **WHEN** the report cites `[4]`
- **THEN** `report.json` resolves it to the source of passage 4 and the passage carries record ID `sunat`

### Requirement: Catalog report in the result
`catalog.json` SHALL carry `output`. `GET /api/runs/{id}/export` SHALL
export a catalog run's report as it does a research run's, and SHALL
answer `no_report` for a catalog run with `output` `table`.

#### Scenario: Export a catalog report
- **WHEN** a client requests the PDF export of a catalog run with `output` `both`
- **THEN** the response is the PDF of its `report.md`

#### Scenario: Export a table-only catalog
- **WHEN** a client requests the export of a catalog run with `output` `table`
- **THEN** the response is 404 `no_report`
