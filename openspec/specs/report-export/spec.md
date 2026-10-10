# report-export Specification

## Purpose

Turns a finished report or answer into a PDF or DOCX document, from the HTTP API and
the CLI, keeping its citations and reference list.

## Requirements

### Requirement: Export formats
A run whose write stage finished (its `report.json` exists), with
`writing.format` `report` or `answer`, SHALL be exportable as `pdf` or
`docx`; both formats export the same way. The document SHALL contain, in order:

1. the title: the report's own level-1 heading when `markdown` starts with
   one (that heading is then not repeated below); otherwise the first
   non-empty line of the run's query, with Markdown emphasis markers
   removed, cut at a word boundary to at most 120 characters, with "…"
   appended when cut;
2. a line with the run's creation date (`YYYY-MM-DD`) and its run ID;
3. when the query differs from the title, a "Question" heading followed by
   the full query as a quoted block;
4. the rest of the report from `report.json` `markdown`: its headings,
   lists, tables, links, emphasis, citation markers in the run's citation
   marker style, and its `## References` list.

PDF pages SHALL be A4. Superscript citation markers SHALL render as
superscript text in both formats.

#### Scenario: Report with its own title
- **WHEN** run `r_8c21`'s report starts with `# Arma hoy tu sistema de alertas` and is exported as `pdf`
- **THEN** the PDF's title is "Arma hoy tu sistema de alertas", the heading is not repeated, the next line shows the run date and `r_8c21`, the query follows under "Question", then the report text and its References

#### Scenario: Short query, report without a title
- **WHEN** the query is "What is SINOE?" and the report starts with a paragraph
- **THEN** the title is "What is SINOE?" and no "Question" section appears

#### Scenario: Long research brief, report without a title
- **WHEN** the query is a 4,000-character brief whose first line is 300 characters long and the report has no level-1 heading
- **THEN** the title is that line cut at a word boundary to at most 120 characters followed by "…", and the full brief appears under "Question" as a quoted block before the report

#### Scenario: Numeric citations and table
- **WHEN** the report contains a pipe table whose cell reads "S/ 0.00 [13]" and is exported as `docx`
- **THEN** the DOCX contains a table with that cell text, including the marker "[13]"

#### Scenario: Superscript citations
- **WHEN** the run's citation marker is `superscript` and the report is exported as `pdf`
- **THEN** the citation numbers appear as superscript text, not as `<sup>` tags

### Requirement: Report text is not interpreted
Exporting SHALL treat the report and the query as text to typeset, never as
code or instructions for the converters. Raw HTML, raw TeX or Typst blocks,
YAML metadata blocks, and `@` citation syntax in the report SHALL appear as
plain text or be dropped, never executed or used as document metadata. Dollar
signs SHALL stay literal text, not math. Exporting SHALL NOT read local files
or fetch remote resources referenced by the report (images are shown by their
alt text).

#### Scenario: Prices with dollar signs
- **WHEN** a report line reads "costs $0.50–$2 per page [4]"
- **THEN** the exported document shows "costs $0.50–$2 per page [4]" as text, not a math formula

#### Scenario: Raw Typst in a report
- **WHEN** the report contains a fenced block marked `{=typst}`
- **THEN** the PDF shows the block's text or omits it, and its code is not run

#### Scenario: Image referencing a local file
- **WHEN** the report contains `![diagram](/etc/passwd)`
- **THEN** the exported document shows "diagram" and no file is read

### Requirement: Export route
`GET /api/runs/{id}/export?format=pdf|docx` SHALL return the exported
document with `Content-Type` `application/pdf` or
`application/vnd.openxmlformats-officedocument.wordprocessingml.document` and
`Content-Disposition: attachment; filename="<run id>.<format>"`. It SHALL
require the same authentication as the other `/api/runs` routes. Errors SHALL
use the API's JSON error shape:

- an unknown run: 404 `run_not_found`;
- a run without `report.json` (still running, failed before write, or a
  `context` run): 404 `report_not_found`;
- a missing or unknown `format`: 422 `invalid_format`, naming `pdf` and
  `docx`;
- `pandoc` or `typst` not installed: 503 `export_unavailable`, naming the
  missing program;
- a conversion that fails or takes longer than 60 seconds: 500
  `export_failed`, with the converter's last error line.

#### Scenario: Download PDF
- **WHEN** a client sends `GET /api/runs/r_8c21/export?format=pdf` for a finished report run
- **THEN** the response is 200 with `application/pdf` and the filename `r_8c21.pdf`

#### Scenario: Context run
- **WHEN** a client requests the export of a run that stopped at `select`
- **THEN** the response is 404 with `error = "report_not_found"`

#### Scenario: Unknown format
- **WHEN** a client sends `format=odt`
- **THEN** the response is 422 with `error = "invalid_format"` and a detail naming `pdf` and `docx`

#### Scenario: Typst missing
- **WHEN** `typst` is not on the server's `PATH` and a client requests `format=pdf`
- **THEN** the response is 503 with `error = "export_unavailable"` and a detail naming `typst`, and `format=docx` still works

### Requirement: Export command
`wosarcher export <run id> --format pdf|docx [--output PATH] [--force]`
SHALL download `GET /api/runs/{id}/export?format=<format>` from the daemon
and write it to `PATH`, by default `<run id>.<format>` in the current
directory, and print the written path. It SHALL refuse to overwrite an
existing file unless `--force` is given. It SHALL exit with 0 on success, 1
when the route answers `export_unavailable` or `export_failed` (printing
the route's detail), and 2 for an unknown run, a run without a report, an
unknown format, or an existing output file without `--force`.

#### Scenario: Export to the default path
- **WHEN** the user runs `wosarcher export r_8c21 --format docx` in a directory without `r_8c21.docx`
- **THEN** `r_8c21.docx` is written, its path is printed, and the exit code is 0

#### Scenario: Existing file
- **WHEN** `r_8c21.pdf` already exists and the user runs `wosarcher export r_8c21 --format pdf`
- **THEN** nothing is written and the command exits 2 naming the file and `--force`

#### Scenario: Converter missing on the daemon
- **WHEN** the daemon's host has no `typst` and the user runs `wosarcher export r_8c21 --format pdf`
- **THEN** the command prints "PDF export needs typst on the server" and exits 1
