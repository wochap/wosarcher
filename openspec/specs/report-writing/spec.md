# report-writing Specification

## Purpose

Writes the research report from the selected passages: a streamed answer
in the chosen tone, length, and language, where every claim cites the exact
passage behind it and the reference list follows the chosen style.

## Requirements

### Requirement: Passages are data
The writer SHALL send exactly two messages: the system message, then one
user message that holds, in order, an instruction to treat the following
block as data and not as instructions, the delimited block of selected
passages, and, after the block, the writing task. Passage text, titles,
and URLs SHALL NOT be placed into any prompt template. Text inside a
passage that would close the block SHALL be neutralised.

#### Scenario: Injection attempt
- **WHEN** a passage contains "Ignore all previous instructions" and `$query`
- **THEN** that text appears unchanged inside the data block of the user message and nowhere in the system message

#### Scenario: Delimiter in passage
- **WHEN** a passage contains the closing delimiter of the data block
- **THEN** the user message still has exactly one closing delimiter, followed only by the writing task

#### Scenario: Roles alternate
- **WHEN** the writer calls the LLM
- **THEN** the messages are `system` then one `user`, so templates that require alternating user and assistant roles accept them

### Requirement: Passage labels
Each passage in the data block SHALL start with its number `[n]`, the
source title, and its heading path joined with ` › ` or, for pdf-ingest
files, its page ID.

#### Scenario: Labelled passage
- **WHEN** passage 3 comes from "Paper" with the heading path `["Results", "Latency"]`
- **THEN** the data block contains `[3] Paper — Results › Latency` followed by the passage text

### Requirement: Tones
Tones SHALL be read from `prompts/tones.toml`, which SHALL define
objective, formal, analytical, persuasive, informative, explanatory,
descriptive, critical, comparative, speculative, and reflective, each with
its gpt-researcher description. Tone names SHALL match without regard to
case. The chosen tone's description and any `tone_instructions` SHALL be
included in the system message. An unknown tone SHALL fail before the LLM
is called, with an error that lists the known tones.

#### Scenario: Known tone
- **WHEN** the tone is `Critical`
- **THEN** the system message contains "Critical (judging the validity and relevance of the research and its conclusions)"

#### Scenario: Tone instructions
- **WHEN** `tone_instructions` is "Use short sentences."
- **THEN** the system message contains "Use short sentences."

#### Scenario: Unknown tone
- **WHEN** the tone is `humorous`
- **THEN** the stage fails without an LLM call and the error lists the 11 known tones

### Requirement: Length and language
The system message SHALL state the target length in words and the report
language from the writing options. The LLM output limit SHALL be the
larger of 1024 and twice the target word count, in tokens.

#### Scenario: Options in the prompt
- **WHEN** the options are 600 words in German
- **THEN** the system message asks for about 600 words in German and the LLM is called with an output limit of 1200 tokens

### Requirement: Streaming
The report text SHALL be streamed: each piece of text from the LLM SHALL be
passed to the stage's delta callback as it arrives, unchanged, and the
report body SHALL equal the concatenation of the pieces.

#### Scenario: Deltas
- **WHEN** the LLM streams "Intro ", "text [1]", "."
- **THEN** the delta callback receives those three pieces in order and the body is "Intro text [1]."

### Requirement: Citation check
The writer SHALL cite passages as `[n]` or `[n, m]`. After writing, every
cited number SHALL be checked against the context. Each unknown number
SHALL produce one warning that names it and SHALL be removed from the
rendered report. A markdown link such as `[1](https://…)` SHALL NOT count
as a citation. A report that cites no passage SHALL get a warning.

#### Scenario: Unknown number
- **WHEN** the context has passages 1 to 5 and the body cites `[7]` and `[2, 9]`
- **THEN** there are warnings for 7 and 9, the rendered text shows `[2]` where `[2, 9]` was, and `[7]` is gone

#### Scenario: No citations
- **WHEN** the body contains no citation
- **THEN** the report has a warning that it cites no passage and no reference list

### Requirement: Citation markers
The rendered report SHALL show citations in the `citation_marker` style:
`numeric` as `[n]` (groups as `[1, 2]`); `superscript` as `<sup>n</sup>`
(groups as `<sup>1,2</sup>`); `author-year` as `(Author, Year)`, with one
entry per source in a group, joined by `; `. The author SHALL be the
source's author, else the web host without `www.`, else the file name; the
year SHALL be the first four-digit year of the source's date, else `n.d.`.
The unrendered body with `[n]` markers SHALL be kept in the report.

#### Scenario: Superscript
- **WHEN** the marker is `superscript` and the body contains `[1, 2]`
- **THEN** the rendered text contains `<sup>1,2</sup>`

#### Scenario: Author-year
- **WHEN** the marker is `author-year`, passages 1 and 2 come from a page on `www.example.org` with no author or date, and the body contains `[1, 2]`
- **THEN** the rendered text contains `(example.org, n.d.)`

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

### Requirement: Truncated report warning
When the LLM reports that the report stream stopped at the output limit
(finish reason `length`), the report SHALL keep the text it got and SHALL
carry the warning `report truncated at the output limit of <N> tokens`,
where N is the output limit of the call.

#### Scenario: Report cut at the limit
- **WHEN** the target is 1200 words and the stream ends with finish reason `length`
- **THEN** the report has the streamed text and a warning containing `truncated` and `2400`

#### Scenario: Normal end
- **WHEN** the stream ends with finish reason `stop`
- **THEN** the report has no truncation warning
