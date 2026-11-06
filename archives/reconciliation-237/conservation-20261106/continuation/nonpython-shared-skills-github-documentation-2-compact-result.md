# nonpython-shared-skills-github-documentation-2: COMPLETE

I read the whole packet: the index and `.txt` lines 1-300, 301-600, 601-900, 901-1200, 1201-1500 and 1501-1819. Nothing in the packet is unread.

Current evidence is from the final combined worktree (`.tools/checkpoint-conservation-final-worktree`, 1eb10a1f). All 23 PRs remain **HOLD**. Nothing here is visual, and the browser, provider and owner gates are separate.

**Exact-blob entries:** I judged these by unchanged bytes plus a check that their consumer or path still exists:
- `host/publication/README.md` and `host/publication/ingestion/README.md` (PR 223);
- `docs/features/github/connection.md` (PR 224);
- `github/pull_requests/README.md` (PR 224);
- `host/leases/README.md` (PR 229);
- `github/issues/README.md`, `github/transport/README.md` and `github/transport/git/README.md` (PR 231).

## Dispositions

| PR / path | Disposition | Current evidence |
|---|---|---|
| 222 `github/pull_requests` and `github/issues` README handler sections; 224 removal of them | **INTENTIONALLY_SUPERSEDED** by the C3 interface move | The vocabulary moved to `github/interface/{issues,pull_requests}/README.md` (e.g. `interface/issues/README.md:11`). |
| 222 `http/README.md` | **PRESERVED**; the `_NoRedirect` alias is **INTENTIONALLY_SUPERSEDED** | `:23` says no compatibility alias remains. Retained probes are adapted by the test loader (tests-5 evidence). |
| 222 / 223 / 224 / 226 / 232 `skills/README.md` (five versions) | **PRESERVED**, except one link | The final text matches PR 232's: concerns, nomenclature and dependency direction (`:13-53`). The `agents/workspaces` link is broken → D2. |
| 222 / 224 / 232 `skills/operations/README.md` | **PRESERVED** | `:17,39` (PR 232 content). |
| 222 / 224 / 228 `skills/sources/README.md` | **PRESERVED** (condensed) | **Collaborators:** `GitSkillSource`, `SkillSourceStagingDirectory` (`:12-44`).<br>**Production profile:** `ISOLATED_HTTPS_READ_ONLY` (`:54`).<br>**Cache budget:** 128 MiB (`:69`).<br>**Client forwards only `repository_cleanup_unverified`:** `:79,92`. |
| 223 `host/publication/README.md` (exact) | **PRESERVED** | — |
| 223 `host/publication/ingestion/README.md` (exact) | **PRESERVED**, with a stale reference | D1 |
| 224 `connection.md` (exact), `walkthrough.md` | **PRESERVED** | The interface CLIs are in `walkthrough.md:80,88` and `sources.md:29`. |
| 224 `github/README.md`; 231 rewrite | **PRESERVED** (final PR 231 form) | `:36` and the layout. |
| 224 `github/interface/README.md` and its issues/PR leaves | **PRESERVED** | Present; checked via `interface/issues/README.md:11`. |
| 224 `skills/interface/README.md` and its operations/sources leaves | **PRESERVED** (my assumption, see Not inspected) | The leaf files exist. The CLI names are confirmed through the docs. |
| 225 `host/private_state/README.md` | **PRESERVED** | **SIWC split:** `:7-8,25-27`.<br>**pywin32:** `:33-35`.<br>**Pending-receipt warning:** `:42`. |
| 226 `skills/registry/README.md` | **PRESERVED** | Method table at `:45`. |
| 227 then 229 `host/leases/README.md` | **PRESERVED** (exact PR 229 blob) | — |
| 228 `git/README.md`, `git/windows/README.md` | **PRESERVED**; `GitTreeEntry` **INTENTIONALLY_SUPERSEDED** | **Budget model:** `GitExecutionBudget` (`git/README.md:15`).<br>**Windows containment:** `:17`, and `windows/README.md:16`.<br>**Read-only profile:** `:51`.<br>The settled supersession is `GitTreeEntry` → `SkillRepositoryEntry`. |
| 230 `src/laomedo/README.md` | **PRESERVED** (rewritten) | **Layout and vocabulary:** `:6-48`.<br>**Defining-symbol and lazy imports:** `:45-48`.<br>Minor omissions → S1. |
| 231 `github/issues/README.md` (context reader), `transport/README.md`, `transport/git/README.md` (exact) | **PRESERVED** | `mediated.py` exists (frozen GitHub249). |
| 234 `user-stories.md` | **PRESERVED**; part **INTENTIONALLY_SUPERSEDED** | The acceptance criteria are at `:50-62`. "Escape closes Find first" was replaced by the later workspace search (`:54-55`). The `67177b1` failure record was provenance and was rightly dropped. |

## Findings

**nonpython-shared-skills-github-documentation-2-D1 — defect, low. Owners: host publication and the migration tool.**
- **What's wrong:** the unchanged `host/publication/ingestion/README.md` (PR 223, packet lines 245-251) points readers at `tools/migrations/retained-ingestion-callers.json`.
- **Evidence:** that file doesn't exist in the final tree. Only `tools/migrations/retained-shared-callers.json` remains, because retained callers were consolidated into the shared loader.
- **Effect:** the active README names a missing inventory.
- **Same pattern elsewhere:** the http README was updated correctly; the ingestion README was not.

**nonpython-shared-skills-github-documentation-2-D2 — defect, low. Owner: Skills docs.**
- **What's wrong:** the final `skills/README.md:50` links to `../agents/workspace/README.md` (singular).
- **Evidence:**
  - Only `agents/workspaces/README.md` (plural) exists.
  - PR 232's text used the plural (packet line 1702).
  - The singular directory holds only cache remnants (settled in T2-I1).
- **Effect:** the declarative README's ownership link is broken. This mirrors the T2-I1 path regression, in docs.

**nonpython-shared-skills-github-documentation-2-S1 — suggestion. This is about docs.**
- **What's missing:** compared with PR 230, the final `src/laomedo/README.md` vocabulary table omits:
  - the `BaseAgent` abstract-contract role;
  - `github/interface/` from the app-boundary row (only Skills is named, at `:38`).
- **Why it's minor:** both still exist and are documented in their owner READMEs.

**Carried forward:** all earlier T1–T5, C4–C6, nonpython-runtime-build, frontend and documentation-1 findings (D1–D3, Q1, S1).

## Not inspected

- The full text of the three `skills/interface/*` READMEs. I confirmed the files exist and that the CLI names are used elsewhere.
- Whether symbols named only in the exact-blob READMEs exist in `src`.
- The frozen owner heads' copies, where they may differ from the final tree.