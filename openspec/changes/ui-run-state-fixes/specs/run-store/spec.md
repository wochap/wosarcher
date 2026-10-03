# Spec Delta

## MODIFIED Requirements

### Requirement: Fork
`fork <run_id> --from <stage>` SHALL create a new run that copies
`attachments/` and the artifacts of every stage before `<stage>`, logs a
`stage.done` for each copied stage marked as copied, and continues from
`<stage>` with the parent's saved configuration plus the new overrides. The
copied `stage.done` SHALL name in `copied_from` the run that executed the
stage: the parent's own `copied_from` for that stage when the parent copied
it too, else the parent. Secrets that are redacted in the saved
configuration SHALL be taken from the current environment and profile.
Forking from a stage whose earlier stages are not all finished SHALL fail
and name the first unfinished stage.

#### Scenario: Rewrite only
- **WHEN** the user forks a finished run from `write` with `--set write.tone=critical`
- **THEN** the new run reuses the parent's `context.json`, makes no search, fetch, or scorer request, and writes a new report with tone `critical`

#### Scenario: Fork of an unfinished run
- **WHEN** the parent run stopped after `fetch` and the user forks from `score`
- **THEN** the fork fails with an error naming `chunk` as the first unfinished stage

#### Scenario: Fork of a fork
- **WHEN** run A ran every stage, B is a fork of A from `score`, and C is a fork of B from `write`
- **THEN** C's copied `stage.done` events for `plan` through `prefilter` have `copied_from = A`, and those for `score` and `select` have `copied_from = B`

### Requirement: Lineage
A new run SHALL have version 1 and no parent. A fork SHALL record its
`parent_run_id`, SHALL have as version the highest version among the runs
of its lineage (the root run without a parent and every run whose parent
chain reaches it) plus one, so no two runs of a lineage share a version,
and SHALL record the overrides it added over the parent.

#### Scenario: Second fork
- **WHEN** run A (version 1) is forked to B, and B is forked to C
- **THEN** B has version 2 and parent A, and C has version 3 and parent B

#### Scenario: Two rewrites of the first version
- **WHEN** run A (version 1) is forked to B (version 2), and A is forked again to D
- **THEN** D has version 3 and parent A
