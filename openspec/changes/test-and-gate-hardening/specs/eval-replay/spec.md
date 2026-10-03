# Spec Delta

## MODIFIED Requirements

### Requirement: Judged precision
`python -m evals.judge` SHALL, only when run explicitly, ask the configured
`llm` which selected passages of each result are relevant to the run's
query, and record precision as relevant passages divided by selected
passages. Passages SHALL be sent in a separate message from the
instructions and never through a template. An answer that cannot be
parsed, including text without a JSON list and a list that is not valid
JSON, SHALL record precision as missing, not zero, and the judge SHALL go
on with the next result. Judgements SHALL be saved so a second run does not
call the model again.

#### Scenario: Precision
- **WHEN** a result has 4 selected passages and the judge answers `[0, 2]`
- **THEN** its precision is 0.5

#### Scenario: Unparsable answer
- **WHEN** the judge answers text without a JSON list
- **THEN** the result's precision is missing and the judge continues with the next result

#### Scenario: Malformed list
- **WHEN** the judge answers `[1, 2,]`
- **THEN** the result's precision is missing, the judge continues with the next result, and it exits 0

### Requirement: Recorded-run fixture
The repository SHALL contain, tracked in version control, a small recorded
run directory produced by `wosarcher run` from recorded SearXNG, Firecrawl,
and LLM responses, with every artifact of a finished run, and a script that
regenerates it from those responses. The fixture SHALL contain no absolute
path of the machine that generated it. Every artifact in the fixture SHALL
parse with the current contract models, and the tests that use it SHALL
pass on a fresh clone without regenerating it.

#### Scenario: Fixture parses
- **WHEN** the test suite loads every artifact and event of the fixture run
- **THEN** each one parses with its contract model

#### Scenario: Fixture forks
- **WHEN** the fixture run is copied to a temporary runs directory and forked from `score` with `score.provider=bm25`
- **THEN** the fork finishes `select` without any network request

#### Scenario: Fresh clone
- **WHEN** the repository is cloned and `git ls-files tests/fixtures/runs` is run
- **THEN** every file of `tests/fixtures/runs/20260101-000000-fixture/` is listed

#### Scenario: No machine paths
- **WHEN** the fixture is regenerated in a temporary directory
- **THEN** no fixture file contains that temporary directory's path
