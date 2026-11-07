# Migration corrections recheck and test boundary packet (head `2e2be4c6`)

The three migration questions are resolved, or settled as far as the source allows. The test packet is mostly sound, but it silently drops the error-catalogue duplicate-key guard (T-D1). That's the one confirmed weakening, and it's small to restore.

## What I read

- **`migration-final-corrections.txt`, lines 1–358 (all of it):**
  - the `test_bytes` additions, migrator README and `manual-symbols` changes;
  - the colon-launcher refusal in `migrate_module_paths.py`;
  - the `symbol-paths` changes;
  - the historical `serve()` tail from `5ad2d01d^`;
  - the six current server constructors.
- **`test-own-boundaries.diff`, lines 1–4117 (the end of the file).**
- **Narrow checks:**
  - `components/laomedo/bounded_controller.py` imports `HttpAgentBridge` lazily, at lines 84–87;
  - a grep of `tests/` for a duplicate-key guard found no match.
- **Not opened:**
  - the JSON data files used as test inputs (`projector-records.json`, `status-records.json`, `request-records.json`, `examples/data/*.json`, `frozen-flow.json`, `corpus.json`);
  - `support/model_contracts.py`, `support/http_server.py`, `test_runtime/models.py`;
  - the parts of the test files outside the diff hunks.

## Task 1: migration recheck

**A-MG-Q1 (colon-style launchers): resolved** (`migrate_module_paths.py:226-232`)
- `migrate_source` now refuses any `laomedo.x.y:` reference whose module is a retired key or a retired split module, before doing anything else.
- It covers:
  - JSON launcher fields, which go through `_migrate_selected` → `migrate_source`;
  - Python string literals;
  - a `python -m … module:attr` command.
- The refusal happens during planning, so no file or backup is written. The CLI test checks exit code 2, unchanged bytes and no backup file.
- Current colon launchers and unselected saved values are left alone.
- **Side effect:** any text such as a docstring that contains a retired `module:` is also refused. That fails closed, which is acceptable for a tool you only run on files you select.

**A-MG-Q2 (functions mapped to classes): settled as far as the source allows**
- **`local_runner.serve` → `RunnerServer`:** the historical tail shows `serve` *returned* an unstarted `ThreadingHTTPServer`, with the same startup-gate sequence: check `.cancel`, bind, touch `listening`, return. The current constructor keeps bind, return and caller-owned serving. Return behaviour matches.
- **Missing evidence:** the excerpt starts mid-function, so the original **`def serve(...)` signature line**, meaning its parameter order and defaults, isn't shown. Positional calls such as `serve(runner, host, port)` are only checked against today's `(runner, host="127.0.0.1", port=8765)` if that header matches. The `loopback_only` refusal is also not visible in the old tail.
- **GitHub, Skill and Join factories:** you say these existed at the accepted base, so they're outside this cut and I accept that. The Join call shape `(controller, token, port=…)` matches the current test.
- **Handler factories:** the crossed `_handler` → `LeaseHTTPServer` mappings are removed and now refused in every form, including the plain-text form (`patch("…_handler")`). That is tested.

**A-MG-Q3 (OpenCode worker pins): resolved**
- Both old paths now map to `opencode.settings.WORKER_IMAGE` and `WORKER_IMAGE_ID`, and the test checks the exact rewritten import.

**A-MG-S1 (map key that is also a current package): accepted as a documented tool limit**
- It's now pinned by `test_interfaces.py:731`, which asserts `reused_packages == {"laomedo.agents.artifacts"}`.

**Migration verdict: APPROVE.** The only open point is the missing `serve` signature line, which is a question.

## Task 2: test boundary packet

**T-D1 · confirmed weakening · low–medium** (`test_catalogue.py`, diff lines 3004–3017)
- `test_catalogue_keys_are_unique` is deleted. It loaded the node error catalogue with an `object_pairs_hook` that refused duplicate keys.
- A grep of `tests/` found no replacement.
- Python's `json.loads` keeps the last duplicate silently, so a pasted catalogue entry could override another code's title and recovery text, with no test failing.
- This was introduced in this own diff. Restoring the test is a few lines. Is there a frontend-side check I haven't seen?

**T-Q1 · question · low** (`test_output.py`, diff lines 1000–1034)
- `test_native_request_queue_answers_precheck_before_turn_ack` is removed together with the old app-server request queue, which is legitimately retired.
- The replacement test checks precheck results through `CodexController._precheck`, but not the *ordering*: that a precheck is answered while the turn is still running, before it completes.
- That ordering now lives in the ACP extension, whose `item/tool/call` handler sends the request to the host. Please point to the provider-packet test that covers it.

**T-Q2 · question · low** (`test_boundaries.py:389-393`)
- The guard that shared code never imports a concrete provider or credentials now scans only `agents/agents/base`.
- `agents/interface` has its own guard (`test_interfaces.py:691`).
- `agents/activity`, `agents/orchestration`, `agents/workspaces` and `agents/artifacts` have none. A shared projection could start importing a provider module without any test failing.

**T-S1 · suggestion · low**
- Some guards only check that a literal string appears in a source file (`test_settings.py:171-182`, the protected-environment expressions). They certify the implementation's wording rather than its behaviour. This style is carried from base and is acceptable as a tripwire.

**Changes that strengthen the tests:**
- **Architecture:**
  - both scan guards now fail if a scan finds nothing, and this is tested by patching `rglob` to return nothing;
  - each provider must be found by the scan;
  - the dependency pin must match between `pyproject` and `uv.lock`;
  - retired module files and directories must stay absent;
  - model field descriptions are required;
  - module-level classes are required, and each class-owning leaf must have a README;
  - imports must bind direct symbols;
  - the join handler and server must be defined at module level.
- **Error catalogue:** new tests check:
  - producer coverage for the OpenCode, lease and working-state codes;
  - that those codes reach the routable list;
  - neutral recovery text, banning "operator", "retry", "restart" and "login";
  - ACP `request_timeout:<method>` routing;
  - that `HistoryError` is a public error type.
- **Bridge (`test_bridge.py`):**
  - a start transport failure never resends, never exposes `PRIVATE`, and leaves no active entry;
  - a poll failure keeps the run that was already acknowledged;
  - the controller reports nonterminal or unknown status as `dispatch_uncertain` with one submission.
- **Activity:**
  - wire order, omitted fields and object identity are preserved;
  - nesting 300 levels deep isn't rejected by validation;
  - application metadata stays strict;
  - modules import cleanly in every order, each in a fresh process;
  - the OpenCode capture-completeness table.
- **Migration:** colon launchers, handler strings, worker pins, the split-workspace symbols, refusal of the `run=` and `**kwargs` forms, map targets with real owners, manual prefixes not shadowing automatic ones, the `settings` partial split, and a code-hash check against the real `lfx` `_generate_code_hash`.
- **Settings:** numeric budgets reject `0`, `-1`, `nan`, `inf` and non-numeric values without echoing the input.
- **Stage:** the runtime-distribution table, and the new `content_digest` in the stage-launch grant.

**Moves only (assertions unchanged):**
- import and patch-target swaps, with `urlopen` → `_HTTP.open` or `HttpAgentBridge._open`;
- path moves into `test_examples/data` and `fixtures`;
- execution-mode strings updated to the ACP values (`codex_acp`, `opencode_acp`);
- mojibake fixed in two Unicode literals, so the tests now really exercise `λ`.

**Checked against wrong-target patching:**
- `test_bounded_controller` patches the module attribute, which works because the component imports inside the function.
- No test imports a retired module.

**Removals that are justified:**
- the exp104 retained-entrypoint test, since experiments moved to `exp`;
- the `_turn_available` method, now asserted absent;
- the `if __name__` block.

**Fixture handling:** `test_src_saved_flow` re-pins the archived fixture's hash only inside the helper, and a separate test proves the normal tool refuses the stale revision. That's honest as a control, not acceptance.

**Test packet verdict: REVISE (narrow).** Restore the duplicate-key guard (T-D1). T-Q1 and T-Q2 are questions. Nothing here counts as provider or graph acceptance.

## Remaining coverage

- **Test packets not yet reviewed:** providers (8,757 lines) and shared (7,404 lines). T-Q1 depends on them.
- **Not opened in this packet:** the JSON data files, `support/model_contracts.py`, and the unchanged bodies of the moved tests.
- **Still open from earlier:** the `serve` signature line (Q2).
- **Gates unchanged:**
  - the migration-correction CI run is pending;
  - wheel parity at 340 files;
  - the TypeScript baseline is still red (259 vs 265);
  - the spec 403 link fix;
  - issue #215 and the paths not retested.

This isn't approval of the whole PR or a merge. PR250 stays a draft, the 23 old PRs stay on hold, and your graph validation is still needed.