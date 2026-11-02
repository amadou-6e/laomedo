# EXP-78: native Codex skill discovery

Issue: [Laomedo #78](https://github.com/amadou-6e/laomedo/issues/78).

## Frozen credential-free route

Use a disposable private `HOME`, `USERPROFILE`, `APPDATA`, `LOCALAPPDATA`,
`CODEX_HOME`, temporary directory, and project. Place exactly one synthetic
`SKILL.md` under the project's `.agents/skills/<name>/` directory. Do not copy
the personal login, settings, sessions, or skills. Hash the source skill before
materialization, the effective private skill before Codex starts, and the
effective skill after Codex stops. Compare personal skill and session roots
before and after without publishing their contents.

Start the installed Codex app-server from a constructed environment. Send only
`initialize` and `skills/list` with the project as `cwd` and `forceReload`.
Do not send `thread/start`, `turn/start`, an explicit skill item, a skill path
in a task prompt, or any model request. Preserve a sanitized result recording
the exact CLI version, fixture name and listing path, path-boundary checks,
hashes, personal-root comparison, and any errors. Raw server logs remain in
the disposable directory and are deleted after the probe.

The expected positive control is that the exact fixture appears once in
`skills/list`, with its path inside the private project and no listed path
under the real personal home. A listing establishes that the skill was
**offered** for selection. It cannot establish that the model read the body
or obeyed it. A separate model-backed comparison of native discovery,
explicit skill input, and prompt mention would require its own credential
decision and submitted-turn cap; this protocol authorizes zero turns.

Record the installed runtime version as a scope limit. Do not generalize the
result to the pinned Docker runner if its Codex build differs. This follows
the [official OpenAI skill description](https://learn.chatgpt.com/docs/build-skills)
that discovery exposes name and description before the full skill body is
read; the local app-server listing itself is the observed evidence here.
