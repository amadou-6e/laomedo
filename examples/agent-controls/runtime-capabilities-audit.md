# Runtime capability discovery and remaining fixed assumptions

Codex model and effort dropdowns now query authenticated GET /v1/models on the configured runner. The runner starts its configured Codex app-server, reads all model/list pages, then closes it; it never starts a thread or turn. Model/effort names and initial defaults are no longer embedded in component source. Refresh explicitly or change Runner URL/model to query again. Saved selections are preserved on load, not silently substituted. Connection failures are explicit errors, not static fallback data.

Live verification: actual local Docker image laomedo-codex-boundary:0.159.2 advertised eight models through the HTTP endpoint. Network disabled, no login mounted, zero model turns. This verifies installed runtime metadata, not account-specific entitlement or execution acceptance. Component HTTP verification is recorded separately when complete.

## Audit scope

Reviewed all product Python components in components/laomedo, their dropdown declarations, and local_runner/opencode_runner capability and version handling. Historical experiment graphs and test data intentionally contain fixed inputs. This is a bounded audit, not a claim that every constant in the repository is unnecessary or discovered dynamically.

## Remaining assumptions

- bounded_controller.py: participants_json defaults to a specific Codex model/low effort. This remains a static example default and should use explicit participants or runtime selection in follow-up.
- opencode_agent.py and opencode_runner.py: only the default variant is supported. Other variants explicitly fail; provider variants are not discovered dynamically.
- local_runner.py and opencode_runner.py: exact CLI versions are pinned (Codex 0.159.2, OpenCode 1.18.33). Codex image IDs/config and seccomp digests are also pinned. These are deliberate tested runtime compatibility/security constraints, not model capability discovery. Upgrading the image requires updating and validating this profile.
- local_runner.py: Git workspace base branch defaults to main when omitted. This can be wrong for repositories with a different default branch.
- Agent operation choices fresh/start/resume/status/cancel, bounded-controller chain/loop, and GitHub state filters open/closed/all are fixed application/API contracts. They are not externally changing model catalogues.
- Skill/revision, issue/PR, and label dropdowns already load registry/GitHub data dynamically.
- Runner/bridge URLs, timeout/retry bounds, Skill count limit, snapshot/body limits, terminal/error status enums and tool allowlists remain configured defaults or policy/protocol constraints. They are not arbitrary runtime capability claims and were not removed in this change.
- Automatic Output Requirements discovery currently recognizes a dedicated Output Contract connection only; ordinary Skill/PR consumers describe proposal formats through their task prompts. Hiding the input did not extend contract discovery.
- Prior Run inputs are hidden for the node interface, but resume/status/cancel still require an underlying reference; durable node-local history selection is not implemented by hiding those ports.
