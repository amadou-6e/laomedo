# Agents

Start with [run and inspect an Agent task](walkthrough.md): ask a useful project
question, choose a model, run once and check the actual answer. If you have not
set up the app and runner, [getting started](../../getting-started.md) includes
the complete local installation and first-run path.

[User stories and visuals](user-stories.md) describe the implemented experience
and clearly labelled proposals.

Agent nodes dispatch provider work through runners and retain run identity and
activity. Domain operations remain with the Skills and GitHub features.

## Architecture and operation

- [Architecture](architecture.md): component, runner, host and activity ownership.
- [Agent activity](activity.md): graph execution navigation, retained messages,
  telemetry and provider-specific limitations.
- [Local runner service](runner/local-service.md): host configuration and recovery.
- [Docker sandbox](runner/docker-sandbox.md): startup policy and pinned resources.
- [Mediated commands](mediation/commands.md) and
  [host services](mediation/host-services.md): supported command scope and authority.

## Providers and evidence

- [OpenCode activity](providers/opencode/activity.md): capture and reconciliation.
- [Codex activity parity validation](providers/codex/activity-parity-validation.md):
  historical evidence with a named revision and bounded acceptance scope.
- [Claude example](../../../examples/claude-agent/README.md): existing provider guide.

See [canonical agent-execution specifications](https://github.com/amadou-6e/specs/tree/main/projects/laomedo/subsystems/agent-execution)
for governing requirements. Validation reports and examples do not establish
acceptance of later revisions.
