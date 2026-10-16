# run-questions Specification

## Purpose

Defines how a run pauses to ask a person questions and resumes with their
answers: the question and answer schema, the pause protocol with timeout and
presence, the clarify pause before any search, and the round and wave pause
cards between rounds.

## Requirements

### Requirement: Questions and answers
A question SHALL have `id` (`q1` to `q4` within a pause), `text`, `kind`
(`confirm`, `single`, or `multi`), `options` (2 to 6, each with `id`,
`label`, an optional `description`, and `recommended`), and
`allow_other` (default false; `single` and `multi` only). For `confirm`
and `single` exactly one option SHALL be recommended; when a model marks
none or several, the first marked, else the first option, SHALL be the
recommendation. An answer SHALL have `question_id`, `option_ids` (one for
`confirm` and `single`, any number for `multi`), and `other` (text, only
when the question allows it; an `other` with no option counts as the
answer). A pause SHALL have `id` (`1`, `2`, …), `kind` (`clarify` or
`round`), `after` (the round or wave, null for clarify), `context` (one
line or empty), `questions` (1 to 4), `created`, `timeout`, `max_wait`,
and, once answered, `answers` and `answered_by` (`user`, `agent`, or
`timeout`). These types SHALL serialise to JSON and parse back to equal
values.

#### Scenario: Recommendation enforced
- **WHEN** a model returns a `single` question with no option marked recommended
- **THEN** the first option is the recommendation

#### Scenario: Other as the answer
- **WHEN** an answer to a `multi` question with `allow_other` has no option and `other` "Add a query about SUNAT"
- **THEN** the answer is valid and its text is used

### Requirement: Pause protocol
A run SHALL pause by writing `input/<id>.json` (the pause) and emitting
`input.needed`, releasing a held GPU model first as the exclusive policy
does between stages. While paused it SHALL check once per second for
`input/<id>.answer.json` and the presence file `input/<id>.hold`. The
deadline SHALL be the later of the pause's creation and the hold file's
last modification, plus `timeout`, and never later than creation plus
`max_wait`; a `timeout` of 0 SHALL continue at once. When the answer file
appears, the run SHALL read it, record it in the pause file with
`answered_by` from the file, emit `input.answered`, and continue. When
the deadline passes without an answer, the run SHALL write the answer
file itself with every question's recommended options, `answered_by`
`timeout`, and continue the same way. The run SHALL keep its slot and its
lock while paused. Cancellation while paused SHALL behave as run-lifecycle
"Cancellation". A fork or rerun SHALL NOT pause: it SHALL reuse its
parent's recorded answers where the pause would have been.

#### Scenario: Answered by the user
- **WHEN** a run is paused and the server writes the answer file with `answered_by` `user` after 20 seconds
- **THEN** within 1 second the run emits `input.answered` with those answers and continues

#### Scenario: Timeout while idle
- **WHEN** a run is paused with `timeout` 60, the hold file was last touched 30 seconds after creation, and no answer arrives
- **THEN** 90 seconds after creation the run continues with the recommended answers and `answered_by` `timeout`

#### Scenario: Presence keeps the run waiting
- **WHEN** the hold file is touched every 10 seconds for 5 minutes
- **THEN** the run stays `waiting` for those 5 minutes

#### Scenario: Ceiling
- **WHEN** `max_wait` is 1800 and the hold file is touched continuously
- **THEN** 30 minutes after creation the run continues with the recommended answers and `answered_by` `timeout`

#### Scenario: Fork does not ask
- **WHEN** a run that answered a clarify pause is forked from `write`
- **THEN** the fork pauses nowhere and its request carries the parent's clarifications

### Requirement: Clarify pause
When the run's `questions.clarify` is on, the `plan` stage SHALL, after
the planner call, make one LLM call: a system message from
`prompts/clarify.md` with only the brief, the topic line, the question
parts, the sub-queries, and the date substituted (for a catalog run, the
`draft` stage after the structure exists, with the brief, the structure's
types, seeds, relation, and limits), and one user message holding the
initial search titles and snippets as data when they exist. The prompt
SHALL ask for up to four questions about scope, sources, depth, and
freshness, each with 2 to 6 options and the recommended option being what
the plan already assumes, and SHALL allow the model to return no question
when the brief is clear. The reply SHALL be checked as Requirement:
Questions and answers; a failed call or an unreadable reply SHALL add the
warning `clarify failed: <reason>` and continue without a pause. With at
least one question the run SHALL pause (kind `clarify`, context "I read
the brief as: <topic line>").

After the answers, the run SHALL record `clarifications` in
`request.json`: one entry per question with its text and the chosen
labels or the `other` text. It SHALL append to the request query a
"Clarifications:" block listing them, so every later stage that reads
the query (gap, write, extract) sees them. When any answer differs from
the recommendation, the planner call SHALL run again with the clarified
query and replace the plan (the topic line, sub-queries, and parts);
otherwise the first plan stands.

#### Scenario: Recommended answers keep the plan
- **WHEN** the clarify pause ends with every recommended answer
- **THEN** no second planner call is made and search starts with the first plan

#### Scenario: Changed answer replans
- **WHEN** the user answers "No" to "Include regional and local governments?" whose recommendation was "Yes"
- **THEN** the planner runs again with the query ending in a "Clarifications:" block that holds that answer, and the new plan replaces the first

#### Scenario: No question
- **WHEN** the clarify call returns an empty question list
- **THEN** the run does not pause and no warning is added

#### Scenario: Clarify off
- **WHEN** the run's `questions.clarify` is false
- **THEN** no clarify call is made

### Requirement: Round pause
When the run's `questions.rounds` is on, a research run SHALL pause after
each gap step that kept at least one follow-up (kind `round`, `after` k,
context the gap note) with no model call, with two questions: `q1`,
`multi`, "Search these next?", one option per kept follow-up (label the
query text, all recommended, `allow_other` with the text used as a new
query); `q2`, `confirm`, "Stop research here and write?", options "No,
keep going" (recommended) and "Yes, write now". After the answers, the
chosen follow-ups SHALL be round k+1's queries in the order kept, and an
`other` text SHALL be added as a query with the next ID and round k+1,
subject to the follow-up rules of research-rounds "Gap step"; when no
query remains, research SHALL stop with `no follow-ups`. "Yes, write now"
SHALL stop research with `stopped by user` and the end note "Research
stopped by the user after round <k>.". A catalog run SHALL pause after
each wave that found at least one new node (context "Wave <k> found <n>
new nodes.") with one `confirm` question "Continue to wave <k+1>?",
options "Yes" (recommended) and "No, assemble now"; "No" SHALL stop the
loop with `stopped by user`.

#### Scenario: Keep two of three
- **WHEN** the gap step after round 1 kept `q6`, `q7`, `q8` and the user keeps `q6` and `q8` and adds "SUNAT organigrama 2026"
- **THEN** round 2 searches `q6`, `q8`, and `q9` "SUNAT organigrama 2026", and `plan.json` marks `q7` dropped by the user

#### Scenario: Stop and write
- **WHEN** the user answers "Yes, write now" after round 2 of a 4-round run
- **THEN** research stops with `stopped by user`, `research.json` has `ran` 2 and that end note, and select and write run

#### Scenario: Timeout keeps going
- **WHEN** the round pause after round 1 times out
- **THEN** round 2 searches every kept follow-up

#### Scenario: Catalog wave
- **WHEN** wave 2 found 14 new nodes and the user answers "No, assemble now"
- **THEN** the loop stops with `stopped by user` and `assemble` runs on the records so far
