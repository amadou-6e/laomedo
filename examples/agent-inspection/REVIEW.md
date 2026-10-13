# Claude review record

Sanitized reviewer conclusions only. Credentials, private transcripts and provider usage metadata are not included.

Inspection code read end to end: runner projection, proxy client, Langflow routes, modal and toolbar patch. Verdict below.

**Verdict: APPROVE** for the first read-only agent-inspection slice (`957fabc..fbfa288`, specs `390e815`). I found no blockers in the projection, proxy or modal. Before activation, settle findings 1–2. The browser checks, the route tests and the host suite are still pending and not counted as passed.

## Findings (none blocking)
1. **Medium (activation): running runners don't have the new endpoints yet.**
   - The endpoints only exist in the new `local_runner.py` (`:1966-1977`). Runners already running older source (8779, 8780, 8784) will answer 404 → "inspection unavailable".
   - Restarting the standing 8780 runner on new source collides with its `reviewed_source == HEAD` policy pin.
   - Before activation, decide which runners to restart, and put only those in `LAOMEDO_AGENT_INSPECTION_URLS`. Re-pin the standing policy explicitly rather than having it fail quietly.
   - The failure itself is safe: an old runner's `/v1/runs/<id>/inspection/…` hits `unknown_endpoint`, so its full-record route is never reached.
2. **Low–medium: a run still being written shows its trace as `invalid`.**
   - `inspect_run` reads `raw-events.jsonl` while the runner may still be appending.
   - A final partial line without a newline fails `json.loads` and sets `trace_status='invalid'` (`agent_inspection.py:113-114`), which reads like corrupted evidence.
   - Treat a final line without `\n` as `incomplete`, or stop before it.
3. **Low: runner inspection errors include raw exception text.**
   - The runner's `do_GET` answers with `error_category = str(exc)` for any `ValueError`/`OSError` (`local_runner.py:1987-1991`). Through the new endpoints that can include JSON parser messages or Windows paths (e.g. a missing `runs` folder in `list_runs`, `agent_inspection.py:133`).
   - Only holders of the runner token see it: both Langflow routes reduce errors to fixed codes (`langflow_skill_viewer.py:62-64,73-74`) and the client discards the body (`agent_inspection_client.py:28`).
   - Still, map inspection errors to fixed codes at the runner.
4. **Low: some counters and history are incomplete.**
   - The budget comes from `state/turn-ledger.json` (`:76-78`). The standing persistent runner keeps per-run ledgers, so it shows "Unknown". That's honest, but the global campaign count isn't available there.
   - `list_runs` returns the first 100 directories in filesystem order (`:131-141`), not the newest. Not guessing a "latest" run is intended, but the order should be stated or sorted by record time.
5. **Low: the cursor parse accepts Unicode digits.** `parts[4].isdigit()` accepts characters like `²`; `int()` then raises a `ValueError`, which becomes a 404 (`local_runner.py:1975-1976`). Harmless, but `[0-9]+` is cleaner.

## What holds
- **Identity:**
  - Run IDs must be canonical UUIDs, and `record.run_id` must equal the path (`agent_inspection.py:64-75`).
  - The proxy requires the response's `summary.run_id` to equal the requested ID (`agent_inspection_client.py:26`), and the modal checks again (`AgentInspectionModal.tsx:38`).
  - The node's own run ID comes only from its Langflow output pool. Records chosen by hand are explicitly labelled as not attested (`:10-15,54`), and no latest run is guessed (`:60`).
- **Metadata only:**
  - The summary includes only these validated fields: IDs, closed status, outcome and error enums, model and effort names, counts, precheck and validation codes with paths that match the field pattern, and JSON syntax line and column (`:79-101`).
  - The answer text is parsed but never returned.
  - Timeline events contain only: event and item type enums, item and turn IDs, the tool name for dynamic tool calls only, the exit code, and the duration. `content_withheld` is always true (`:116-125`).
  - Text, commands, arguments, outputs and error messages are never exported.
- **Malformed evidence:**
  - Paths are checked for links and reparse points up to the root (`:32-43`).
  - The record is limited to 1 MiB, lines to 256 KiB and the trace to 32 MiB.
  - Bad lines give `invalid`, over-limit gives `limited`, a missing trace gives `missing`.
  - A non-dict record is refused.
- **Pagination:** 200 events per page, with the cursor being the line index, at most 1,000,000 lines, and a re-scan bounded by bytes. The modal keeps a previous-page stack (`:80`).
- **Connections and credentials:**
  - The runner URL must *exactly* match an entry in the configured allow-list, use `http`, a loopback or `host.docker.internal` host, and carry no path, credentials, query or fragment (`agent_inspection_client.py:11-15`).
  - The existing transport token is used, redirects are refused, the response is limited to 2 MiB, and its schema is checked.
  - Both routes require Langflow login and an exact key set.
- **Toolbar:** following spec `agent-inspection.md:18`, "Inspect agent" replaces Code only for `LaomedoCodexAgent`, using `nodeKind` so namespaced types match (`upstream.patch:224-236,291-296,352`). The Skill and Issue actions are unchanged.
- **No side effects:** both endpoints are GET or proxy reads only. The UI states that nothing is run, retried or cancelled.

## Limits
- **Not read:** the drawio, the full spec, the projection and route tests, and the README.
- **Not done:** I haven't checked tab switching or abort behavior in a browser, and those checks are still pending on your side.

---

**Verdict:** the source and specs are **approved** (`00a9b98`, specs `ce59be6`). The **activation package needs changes** before it runs: the prepared script does more than the deployment draft says, and it leaves out the controller step the draft depends on.

## Source delta (`fbfa288..00a9b98`): all fixed
- **Incomplete final trace line:** a last line without `\n` now gives `trace_status='incomplete'` and stops (`agent_inspection.py:112-113`).
- **Fixed runner error codes:** any error on an inspection path outside five fixed codes becomes `inspection_unavailable` (`local_runner.py:1989-1990`). Paths and parser text no longer leak.
- **ASCII cursor:** `isascii() and isdigit()` (`:1975-1976`).
- **History:** now reports `order: "filesystem"` and `truncated` (`agent_inspection.py:142`), as the contract requires.

## Specs: contract and drawio (now read)
- **Contract** `agent-inspection.md` matches the code. It covers:
  - the toolbar replacement;
  - binding to the current output versus a manual choice, never inferring the latest run;
  - the exact loopback allow-list with the existing backend secret, and no state or profile mount;
  - requested and reported model shown separately, with unknown counters left unknown;
  - closed validation codes, and syntax diagnostics as line and column only;
  - the metadata-only field list, the 32 MiB / 256 KiB / 200 / 1 MiB / 2 MiB / 100 limits, and the explicit trace states;
  - validation requirements including secret canaries, with no streaming, raw content or cost estimates.
- **Drawio:** four pages (Overview, Output validation, Timeline, Empty/Loading/Unavailable/Changed), each with the same header, run dropdown, binding warning, tabs and the read-only Refresh/Close actions. They match the contract and the modal.
  - **Minor gap:** the Timeline page lists `complete / paged / limited / invalid / missing` but not the new `incomplete` state. Add it so the diagram stays the UI authority.
  - The visual check is pending, as you said.

## Activation changes required
1. **The script makes changes the draft doesn't mention.** `activate-agent-inspection.py`:
   - repoints `/app/custom_components` to `claude-review.local/github-issue-components` (`:87`);
   - sets `LAOMEDO_GITHUB_ISSUE_URL`/`TOKEN_FILE` (`:81`);
   - *requires* that a new catalog entry `ext:laomedo:LaomedoGitHubIssue@extra` appears afterwards (`:132-138`).

   So this activation also installs the GitHub Issue component into the viewer's catalog. `AGENT-INSPECTION-DEPLOYMENT.md` says the catalog is preserved and mentions only the inspection frontend and source. Either document the catalog addition and the 8783 settings as part of this activation, with the owner's configuration approval, or remove them from this script.
2. **Catalog code comes from an unpinned folder.** That same mount points at an ignored local folder, not the pinned source revision. The script checks hashes for the frontend build and the source HEAD, but not for `github-issue-components`. Either mount from `work-issue-graph.local/components` at the checked revision, or check a hash manifest of that folder against the reviewed source.
3. **The controller upgrade is missing.**
   - The draft's first step upgrades the 8784/8785 controller to the reviewed source, after checking that its run is terminal, it has no pending work, no owned container, and its state, ledger and lease are preserved.
   - The prepared script only replaces the viewer.
   - Without the controller upgrade, 8784 has no inspection endpoints and Inspect shows "unavailable". That fails safely but doesn't deliver the feature.
   - Add the controller step, with those checks, to the script or as a separate reviewed step that runs before the viewer swap.

## What holds in the script
- It refuses unless:
  - the build matches its manifest, the source is at the manifest revision and clean, the skill registry exists, and the database location is confirmed;
  - no workflow is pending;
  - the baseline is re-checked just before the swap.
- The candidate is created without starting it. It must match the old container's settings exactly, apart from mounts (normalized for Docker Desktop paths), with the expected env, the same image and read-only mounts.
- The old container is renamed for rollback. After the swap, owned flows, database rows, user, catalog and the skill selection must match (apart from the stated catalog addition), and the settings must be 1 worker, 300 s timeout, the components path, the config folder and auto-login.
- Any failure rolls back to the old container.
- The only allow-listed inspector is `http://host.docker.internal:8784`. 8779/8780/8782/8783 aren't touched.

## Limits
- **Not read:** the browser regression script and the native-example pin change. I relied on your test reports (12+1 skip, 3 route tests, the browser sequence, and the targeted 70 tests).
- **Host suite:** the Windows file-lock failure in the host suite is pre-existing and unresolved; I can't confirm it's unrelated.

---

**Verdict: all three activation blockers are resolved. APPROVE the activation package**, with two small fixes recommended before running it (neither blocks).

## The three blockers
1. **Undeclared catalog change: resolved.**
   - `activate-agent-inspection.py` now changes only `PYTHONPATH`, `LANGFLOW_FRONTEND_PATH` and the single inspector allow-list entry (`:80-81`), plus the `/workspace` and `/skill-frontend` mount sources (`:84-85`).
   - The custom-component mount and the skill and issue settings are inherited unchanged.
   - After the swap it now requires `after == before` *exactly*, including the catalog (`:132-140`).
   - The draft says so (`AGENT-INSPECTION-DEPLOYMENT.md:10`).
2. **Unpinned component folder: resolved.** The existing component mount is no longer repointed, so no new code reaches the catalog.
3. **Missing controller step: resolved.** `upgrade-agent-inspection-controller.ps1` runs first and:
   - confirms the exact PID is a `uv.exe` running `graph_demo.py` with this state;
   - requires a clean source tree;
   - requires every run record to be terminal with `attempt_finished`, and no owned containers labelled with those run IDs;
   - refuses if any saved graph has pending work;
   - hashes the ledger, config, records, binding and receipts before and after;
   - kills only that process tree, restarts it from the reviewed source, and waits for `/v1/inspection/runs` to answer with the right schema;
   - re-verifies the hashes and that the independent lease process is still alive.

   No model is dispatched.

## Recommended fixes (not blocking)
1. **The controller script doesn't check the source revision.** It records `$revision` (`:8,40`) but never compares it with the reviewed `00a9b98`. The viewer script compares against its manifest, so a later commit would be caught there, but only after the controller had already restarted on it. Add `if($revision -ne '00a9b98…'){throw}` before `taskkill`.
2. **Hard-coded lease PID, and no undo for the controller.**
   - The lease PID is fixed at `39780` and checked only *after* the restart (`:39`). Check it before `taskkill` as well, so a lease that's already missing stops the run before anything changes.
   - If the new controller fails to start, the old one is already gone and there's no rollback. That leaves Inspect unavailable, a safe state, but note it.
3. **Cosmetic:**
   - the comment at `activate-agent-inspection.py:130` ("Only the reviewed new catalog entry may be added") is stale;
   - the success output still says `catalog_preserved_plus_github_issue: true` (`:150`), which no longer matches the exact-equality check. Rename it, e.g. `catalog_preserved`, so the activation record is accurate.

I read only the scripts and the draft. I ran nothing and didn't open credentials or the private state.
