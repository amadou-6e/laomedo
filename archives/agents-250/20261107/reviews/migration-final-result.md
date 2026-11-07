# PR250 offline migration tool: independent scope review (`02c2c291`)

The migrator handles bytes and files safely, and its refusal rules hold. The earlier fixes M1 and M2 are still in place. I found no confirmed defect, but three map and parsing questions could produce a broken migration that passes without any error. The most important one is that launcher fields in `module:attr` form get rewritten without the symbol check.

I didn't have the base file, so I can't say whether any of this was introduced by PR250 or carried from earlier.

## What I read

- **`migration-final-source.txt`, lines 1–3158 (the end of the file):**
  - `migrate_module_paths.py` 1–989;
  - `module-paths.json` 1–298;
  - `symbol-paths.json` 1–1712;
  - `manual-symbols.json` 1–100, `cli-paths.json` 1–31, `protected-graphs.json` 1–9;
  - `migration_errors.py` 1–5.
- **Narrow checks:**
  - a grep of `tests/` for the function-to-class retargets: `test_langflow_join_http.py:17,45` calls `JoinServer` with the old `serve_langflow_join` call shape;
  - `src/laomedo/agents/artifacts/__init__.py` exists, so that path is a current package.
- **Not read:** `tests/test_shared/test_migration`; the tool and migration READMEs; `agent-history.json`; any base (`bb250135`) version of these files. Glob doesn't work under `.tools`, so I couldn't list current modules to check every map target.

## Checked and found sound

- **Bytes:**
  - Files that need no change are only reported as "current" and never written.
  - In JSON, only the changed string tokens are replaced. Their ASCII escaping follows the original token, and a BOM is kept (`:843-893`, `:947-958`).
  - Invalid UTF-8 is refused (`:949-952`).
- **Writes and backups:**
  - Every input and backup is checked before anything is written.
  - Backups are created exclusively (`O_EXCL`, mode `0o600`).
  - The tool refuses if a file changed after it was read.
  - Each file is replaced atomically through `mkstemp` in the same directory, then fsync, chmod and `os.replace` (`:896-910`, `:969-983`).
  - There is no rollback across a batch; that is the existing low note.
- **Historical evidence:** the protected graph paths are compared after resolving, so only a copy you name explicitly can be migrated (`:929-940`). Symlinked files, non-files and files over 16 MiB are refused.
- **Langflow code hashes:** a hash is updated only if it is 12 hex characters and matches the original source. Anything else is refused. The hash uses the same `migrate_source` output that is written (`:772-819`).
- **Refusals:**
  - manual symbols, as text and through the AST;
  - star imports and dynamic `getattr`, `setattr` and `hasattr` on split modules;
  - fully qualified access to members of split modules;
  - retired module objects passed around;
  - `run=` and `**kwargs` on the changed Git calls (M1, still present at `:212-221` and `:307-318`);
  - tuple unpacking of `capture_for`, the `ActivityStore.start` signature, and container-cleanup identity;
  - positional arguments or `asdict`/`replace` on the models now converted to Pydantic;
  - `LeaseHTTPServer` construction.

  None of these attempts an automatic migration.
- **Saved values:** only code fields, recognised code hashes and the listed launcher fields change. Graph identity and other values are untouched.
- **Map integrity:** the tool checks that no map target is itself an old key (`:34-35`). The manual entries cover each retired protocol, Git helper and workspace namespace with an explanation.

## Questions (ranked)

**A-MG-Q1 · medium · launcher `module:attr` values skip the symbol map** (`:743-747`, `:722`, `:733-740`)
- **Trigger:** a selected launcher field such as `"factory": "laomedo.local_runner:serve"` or `"entrypoint": "laomedo.lease_service:_handler"`.
- **Mechanism:**
  - Python can't parse that value, and it contains no `import` text, so it isn't refused.
  - `SYMBOL_PATTERN` only matches the dotted form.
  - `MODULE_PATTERN` rewrites just the module part, for example to `laomedo.agents.agents.codex.agent:serve`.
  - The final retired-module check passes, because the new module exists.
- **Consequence:** the launcher points to an attribute that doesn't exist, or one with a different meaning, and the run reports it as "migrated" rather than requiring manual work. Starting it would most likely fail loudly, but the tool's promise that it never drops a symbol silently isn't kept here.
- **Suggestion:** either refuse launcher values containing `:` that use an old module, or map the `module:attr` form through `SYMBOL_PATHS`. Are colon-style launchers among the supported inputs?

**A-MG-Q2 · low–medium · old functions mapped to classes** (`symbol-paths.json`)
- **Examples:**
  - `local_runner.serve` → `RunnerServer` (`:1009`; also `agents.local_runner.serve` at `:152`);
  - `*_server.server` → `IssueServer`, `PullRequestServer`, `SkillOperationServer` and `SkillSourceServer`;
  - `serve_langflow_join` → `JoinServer`.
- **Why it matters:** only `LeaseHTTPServer` is refused (`:369`, `:670`). The current `RunnerServer.__init__` only binds the socket; the caller owns serving, as I read last packet.
- **What I found:**
  - The `JoinServer` mapping is supported by a current test, which uses the same call shape.
  - For `serve` and the `server` factories I haven't seen the original functions. If they started serving or took different arguments, the rewritten call returns an unserved object and no error is raised.
- **Question:** can you confirm the base signatures and return behaviour, or add those names to the refusal list?

**A-MG-Q3 · low · inconsistent or crossed targets**
- **Inconsistent:**
  - `opencode_boundary.WORKER_IMAGE` and `WORKER_IMAGE_ID` map to the **Codex** `settings.IMAGE` and `IMAGE_ID` (`:227-228`, `:1046-1047`).
  - `providers.opencode.settings.WORKER_IMAGE` maps to the **OpenCode** `settings.WORKER_IMAGE` (`:1651-1652`).
  - Both may hold the same value today, but one old name gets two different owners.
- **Crossed:**
  - `mediation_service._handler` maps to the **lease** `LeaseHTTPServer` (`:739`, `:1026`).
  - Imports and attributes are refused there. But the plain-text pass at `:722` still rewrites fully qualified strings inside source, such as mock patch targets, to the lease server without refusing.
- **Already handled:** the earlier crossover `opencode_activity.receipt` → shared `runner.feed.receipt` looks like a correct move to a shared helper.

## Optional suggestion

**A-MG-S1 · low · a map key is also a current package** (`module-paths.json:21`)
- `laomedo.agents.artifacts` is a map key, but it is also a current package (`artifacts/__init__.py`).
- Correct current code such as `from laomedo.agents.artifacts import errors` is refused with "No safe symbol mapping" (`:402-410`), and `import laomedo.agents.artifacts` is rewritten to `.utils`.
- This errs on the safe side, but it means running the tool on already-migrated code isn't a no-op for this package. I didn't check other keys for the same overlap.

## Earlier notes

- **M1 and M2:** still fixed.
- **Existing low notes:** no whole-batch rollback (still true); imported names can pass the exported-symbol checks (still true, since targets are checked only by being in the map). The history-manifest digest isn't in these files, so I couldn't recheck it.

## Verdict for the migration scope

**APPROVE with questions.** No defect is confirmed. A-MG-Q1 and A-MG-Q2 should be answered or turned into refusals before you rely on the tool for launcher JSON or server-factory callers.

**Remaining gaps:**
- the migration tests;
- `agent-history.json` and the tool README;
- base comparison, so origin is unknown;
- a check that every map target exists today.

The internal tests are controls, not acceptance. This isn't approval of the whole PR or a merge. The broader gates you listed still stand, the 23 old PRs stay on hold, and your graph approval is still needed.