# Experimental OpenCode adapter

Issue: https://github.com/amadou-6e/laomedo/issues/27.

`laomedo.opencode_runner.OpenCodeRunner` reuses the immutable skill store and
workspace lifecycle. `components/laomedo/opencode_agent.py` provides native
Langflow ports by reusing the existing Codex client. Install the category together
with `components/` on the component server's Python module search path. Nothing
in this change installs it into the running user flow or modifies server settings.

Runtime check: OpenCode 1.18.33, Langflow 1.12.3. Unsupported variants fail, rather
than silently becoming the default. Provider/model is required explicitly. Skills
have OpenCode's kebab-case names; shared registry names with underscores are rejected.

Production transport is intentionally disabled. The existing Codex Docker profile
must not be assumed to protect OpenCode credentials from its native shell tools.
Do not mount the personal authentication file into a same-UID tools container.
The HTTP transport is a protocol adapter for an independently provisioned private
server, not an isolation implementation or an automatic authentication handoff.

No authenticated model call was made. The installed default auth store reports no
credentials; the user's authenticated Go instance remains to be located. Image pin,
actual skill discovery, native cancellation termination and live import/run acceptance
remain incomplete. No new turn cap exists for this ticket; the old Codex ledger is
unchanged. This slice is not merge-ready as fulfillment of #27.

Credential-free tests:

```powershell
python -m unittest discover -s tests
```

The Langflow tests run inside the pinned 1.12.3 image with repository files copied
to a temporary directory, without changing installed components:

```text
python tests/langflow/test_opencode_component.py
python tests/langflow/test_codex_component.py
```
