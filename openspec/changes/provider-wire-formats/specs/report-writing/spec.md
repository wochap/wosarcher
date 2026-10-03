## MODIFIED Requirements

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

## ADDED Requirements

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
