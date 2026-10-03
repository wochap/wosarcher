# Spec Delta

## ADDED Requirements

### Requirement: Doctor reports release and GPU policy
The report printed by `wosarcher doctor --json` SHALL include the resolved
`run.gpu_policy` as `gpu_policy` and, in each provider row, the block's
configured `release` (`none`, `llama-swap`, or `ollama`), also for
built-in providers.

#### Scenario: JSON report
- **WHEN** the user runs `wosarcher doctor --json --profile low-vram`
- **THEN** the report has `gpu_policy` `exclusive` and every provider row has a `release` value matching the profile
