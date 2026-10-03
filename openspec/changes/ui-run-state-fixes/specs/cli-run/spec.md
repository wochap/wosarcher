# Spec Delta

## MODIFIED Requirements

### Requirement: Fork command
`wosarcher fork <run_id> --from <stage>` SHALL accept `--set`, the writing
flags, `--until`, `--profile`, `--run-id`, and `--json`, create a forked
run as the run store defines, and run it to the end or to `--until`. With
`--profile NAME` the fork's settings SHALL be resolved from that profile
and the parent's overrides plus the new overrides, instead of the parent's
saved settings, and the fork SHALL record `NAME` as its profile.

#### Scenario: Change the tone
- **WHEN** the user runs `wosarcher fork <id> --from write --tone critical`
- **THEN** a new run with the next version of the parent's lineage is created and only the write stage runs

#### Scenario: Retry with another profile
- **WHEN** the user runs `wosarcher fork <id> --from score --profile cloud`
- **THEN** the fork's score block comes from the `cloud` profile and its record names profile `cloud`
