# Spec Delta

## MODIFIED Requirements

### Requirement: Profiles
The system SHALL load profiles from TOML files. Built-in profiles ship with
the package. User profiles are read from `$XDG_CONFIG_HOME/wosarcher/profiles/`
(`~/.config/wosarcher/profiles/` when `XDG_CONFIG_HOME` is unset). A user
profile with the same name as a built-in profile SHALL replace it. The
built-in profiles SHALL include `low-vram`, `workstation`, and `cloud`.
A profile MAY set a top-level `description` string: one line that says
what the profile is for. It SHALL NOT be a configuration setting (it is not
part of the resolved configuration and cannot be set by environment or
`--set`). A `description` that is not a string SHALL fail with an error
that names the profile file. A profile without one has an empty
description. Each built-in profile SHALL have a description: `workstation`
"One GPU fits all models; models stay loaded.", `low-vram` "Models take
turns on one small GPU; slower, fits 8 GB.", and `cloud` "Hosted APIs
only; needs API keys.".

#### Scenario: Built-in profile
- **WHEN** no user profile named `cloud` exists and the user selects `cloud`
- **THEN** the built-in `cloud` profile is used

#### Scenario: User profile overrides built-in
- **WHEN** `~/.config/wosarcher/profiles/cloud.toml` exists and the user selects `cloud`
- **THEN** the user file is used and the built-in `cloud` profile is ignored

#### Scenario: Unknown profile
- **WHEN** the user selects a profile name that matches no file
- **THEN** the command fails with an error that names the profile and lists the available profiles

#### Scenario: Description is not a setting
- **WHEN** a user profile starts with `description = "SearXNG on homelab, models on desktop:gpu0."` and the user selects it
- **THEN** the configuration resolves without error and `wosarcher profile show` prints no `description` key

#### Scenario: Invalid description
- **WHEN** a user profile sets `description = 3`
- **THEN** resolving it fails with an error that names the profile file and `description`

### Requirement: Profile commands
The CLI SHALL provide `wosarcher profile list` (one line per profile: a `*`
marking the active one, the name, the source built-in or user in
parentheses, and the description when it is not empty), `wosarcher profile
show [name]` (the fully resolved configuration with secrets redacted), and
`wosarcher profile use <name>`.

#### Scenario: List marks active profile
- **WHEN** the active profile is `cloud` and the user runs `wosarcher profile list`
- **THEN** the output lists every profile with its source and marks `cloud` as active

#### Scenario: List shows descriptions
- **WHEN** the user runs `wosarcher profile list` with only the built-in profiles
- **THEN** the `low-vram` line reads `  low-vram  (built-in)  Models take turns on one small GPU; slower, fits 8 GB.`
