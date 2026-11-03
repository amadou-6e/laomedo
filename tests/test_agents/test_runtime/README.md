# Runtime controls

The suite protects Agent lifecycle, request identity, startup/recovery, accounting,
command completion and failure finalization. Internal transports are doubles; these
checks do not establish real provider or graph acceptance.

`RunnerCase` in `models.py` owns one temporary source, imported Skill receipt and
CodexAgent. `create()` prepares fresh resources and cleans partial setup on failure;
`request()` produces a fresh request bound to that receipt; `close()` releases only
its owned resources. Runtime handles are excluded from model serialization.
`prepare_runner()` binds that case to existing tests without borrowing a TestCase.
`transport.py` defines the shared internal ACP transport. `commands.py` specializes
it at module scope for command events, uncertain cleanup and resumed commands.
`test_commands.py` preserves the dangling-command, terminal status, artifact gating,
redaction, cleanup uncertainty and stale-snapshot assertions across the ACP move.

Run `python -m unittest discover -s tests/test_agents -t tests -v` with the declared
runner dependencies. No campaign, model turn or experiment checkout is required.
