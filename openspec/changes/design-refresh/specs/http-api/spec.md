# Spec Delta

## MODIFIED Requirements

### Requirement: Profiles
`GET /api/profiles` SHALL return every profile with its `name`, its
`source` (`builtin` or `user`), whether it is `active`, and its
`description` (empty when the profile sets none).

#### Scenario: Active profile marked
- **WHEN** the stored default profile is `cloud`
- **THEN** the `cloud` entry has `active = true` and every other entry `false`

#### Scenario: Descriptions
- **WHEN** a client requests `GET /api/profiles` and a user profile `nixos` sets no description
- **THEN** the `workstation` entry has `description` "One GPU fits all models; models stay loaded." and the `nixos` entry has `description` ""

### Requirement: Provider health
`GET /api/providers/health` SHALL run the `wosarcher doctor` checks for the
active profile, or for the profile named by the `profile` query parameter,
and return them as JSON: the profile name, the profile's `gpu_policy`
(`shared` or `exclusive`), the doctor's warnings, and one entry per
provider with `role`, `provider`, `url`, `model`, `device`, `release`
(`none`, `llama-swap`, or `ollama`), `status`, `latency_ms`, and `detail`.
The status SHALL be `down` for a failed probe, `skipped` for a built-in
provider, `degraded` for a probe that succeeded but took more than 1000 ms
or whose model cannot be unloaded although a release is configured, and
`ok` otherwise. No secret SHALL appear in the response. When the checks
cannot run (timeout or unreadable output), the response SHALL be 502 with
the reason.

#### Scenario: Health of a named profile
- **WHEN** a client requests `GET /api/providers/health?profile=cloud`
- **THEN** the response lists the checks for the `cloud` profile

#### Scenario: Slow provider
- **WHEN** the search probe succeeds in 1840 ms
- **THEN** the search entry has `status = "degraded"` and `latency_ms = 1840`

#### Scenario: Unreachable provider
- **WHEN** the score probe fails with a connection error
- **THEN** the response is 200 and the score entry has `status = "down"` and the error as `detail`

#### Scenario: Policy and release
- **WHEN** the checked profile is `low-vram` (`gpu_policy = "exclusive"`, prefilter `release = "llama-swap"`)
- **THEN** the response has `gpu_policy` `exclusive` and the `prefilter` entry has `release` `llama-swap`
