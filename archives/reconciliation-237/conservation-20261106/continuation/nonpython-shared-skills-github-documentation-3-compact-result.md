# nonpython-shared-skills-github-documentation-3: conservation report (read-only)

**All 23 PRs stay on HOLD.** This report approves nothing. Browser, provider and owner gates are separate. I inspected all 1310 packet lines. Nothing in the packet is left unread.

## Inspected ranges

Final worktree (1eb10a1f, under `.tools/checkpoint-conservation-final-worktree`):
- **Read in full:** `AGENTS.md:1-101`, `git/README.md:1-100`, `skills/interface/operations/README.md:1-44`, `skills/interface/sources/README.md:1-20`, `skills/operations/README.md:1-115`, `skills/registry/README.md:1-87`.
- **Partial:** `package-layout.md:1-30`.
- **Searched:** `docs/verification/` (absent). Definers in the `authoring`, `inspection` and `interface/sources` folders. `tests/test_shared/test_architecture/test_packages.py`.

Outside the final worktree, I checked one line of the specs repo: `specs/AGENTS.md:101`.

## Dispositions

| Old entry | Disposition | Current evidence |
|---|---|---|
| 236/238 `AGENTS.md` (the GitHub issue-and-branch workflow section, plus the issue-branch checkpoint wording) | **GAP**, partly superseded | The section is absent. `AGENTS.md:96-98` is back to the older "draft branch/PR" wording. Only `:10` mentions an "own issue branch". The branch-name rule survives in `specs/AGENTS.md:101`. → D1 |
| 238 `node-http-boundaries.md` (the `interface/*` owner paths, the `repository_cleanup_unverified` forwarding note, the alias retirement) | Retired as a document; the earlier finding documentation-1 Q1 already covers this | Forwarding is restated at `skills/sources/README.md:1299-1302` (exact blob). The no-alias rule is at `http/README.md:23`. The per-handler request-cap table has no current home. → Q1 |
| 238 `package-layout.md` (build hygiene for wheels) | **PRESERVED**, condensed | `package-layout.md:18-20`. The installed-artifact check is `test_packages.py:20`. |
| 238 `docs/verification/shared-skills-merge-readiness.md` (added file) | **INTENTIONALLY_SUPERSEDED** as chronology | The folder does not exist. Removing it fits the declarative-README rule. The "acceptance still required" items are only partly carried forward. → Q2 |
| 238 `git/README.md` (restructured into concerns, methods, environment and budgets) | **PRESERVED** | `:10-87` matches the PR238 text. `:89-99` adds an option allowlist and a POSIX limitation. Dropping `GitTreeEntry` from `:15` is a settled supersession. |
| 238 `git/windows/README.md` (exact blob) | **PRESERVED** | Unchanged bytes. The `WindowsProcessTree` binding was checked earlier. |
| 238 `http/README.md` (exact blob) | **PRESERVED** | Unchanged bytes. The no-alias binding was checked earlier. |
| 238 `skills/authoring/README.md` (added, exact blob) | **PRESERVED** | Definers: `authoring/summary.py:8` (`has_description`) and `:45` (`summary_authoring`). |
| 238 `skills/inspection/README.md` (added, exact blob) | **PRESERVED** | Definer: `inspection/utils.py:46` (`inspect_skill`). |
| 238 `skills/interface/README.md` (exact blob) | **PRESERVED** | Unchanged bytes. The `operations/` and `sources/` adapter READMEs both exist. |
| 238 `skills/interface/operations/README.md` (cap, protocol contracts, usage, offline migration) | **PRESERVED** | `:3-8` and `:28-43` match PR238 line for line. Later manual-editor content is mixed in. → S1 |
| 238 `skills/interface/sources/README.md` | **Partly a GAP** | Rewritten as a 20-line module table at `:1-20`. Several PR238 contract statements were dropped. → D2 |
| 238 `skills/operations/README.md` (wording without "existing") | **PRESERVED** | `:14`, `:24`, `:34`, `:42`. |
| 238 `skills/registry/README.md` (store-internal collaboration, offline symbol map, EXP-08) | **PRESERVED** | `:13`, `:20`, `:41-57`, `:67-86`. |
| 238 `skills/sources/README.md` (exact blob) | **PRESERVED** | Recorded inspection: `:12-44`, `:54`, `:69`, `:79`, `:92`. |

## Findings

**nonpython-shared-skills-github-documentation-3-D1: the issue/branch workflow section in AGENTS.md was dropped**
- **Category:** process documentation. Applies to the spec/docs.
- **What changed:** PR236/238 added a local section (old diff lines 11-24). The current file has none of it:
  - a link to the canonical specs workflow;
  - "identify or create the owning issue before branching";
  - "link each PR to its issue";
  - "existing issue edits and closure require explicit approval; do not use closing keywords";
  - pushing to the issue branch and keeping its draft PR up to date. `AGENTS.md:96-98` is back to the generic "draft branch/PR" wording.
- **Mitigation:** the branch-name format survives in `specs/AGENTS.md:101`.
- **Uncertainty:** I did not check whether the specs file also carries the approval and closing-keyword rules. If it does, this finding shrinks to a missing local pointer.

**nonpython-shared-skills-github-documentation-3-D2: contract statements dropped from the sources interface README**
- **Category:** interface documentation. Applies to the spec/docs.
- **Behaviour is unchanged:** the 16 KiB request cap still exists in code at `interface/sources/handler.py:37`, and the response-body bound at `client.py:59`.
- **What the current `interface/sources/README.md:1-20` no longer documents:**
  - the 16 KiB request-body cap;
  - that a response failure after possible dispatch never makes a resend safe;
  - the Settings constraints: explicit arguments or environment only, no dotenv or secret-store lookup, credentials kept in files;
  - the usage paths for the `cli` module and `source_request`;
  - the offline-migration and byte-preserved-archive statement.
- **Contrast:** the parallel operations README keeps all of these (`:33-43`).
- **Uncertainty:** low. The cap now has no documentation anywhere, because `node-http-boundaries.md` was removed.

**nonpython-shared-skills-github-documentation-3-Q1: no current home for per-handler HTTP caps and failure policy**
- **Category:** documentation consolidation. Applies to the spec/docs.
- **Detail:** the removed `node-http-boundaries.md` table held the request caps (1 MiB / 1 MiB / 16 KiB / 4 MiB) and failure policies for all four handlers. It also documented that the Issue and PR allowlists are deliberately different. Only the operations cap survives (`interface/operations/README.md:33`). I did not check the GitHub interface READMEs in this packet.
- **Relation to earlier work:** this extends documentation-1 Q1 rather than reopening it.

**nonpython-shared-skills-github-documentation-3-Q2: acceptance blockers from the retired merge-readiness audit**
- **Category:** acceptance tracking. Applies to the spec/docs and visual.
- **Still documented:** the cleanup-uncertainty discovery story (`skills/sources/README.md:1308-1310`).
- **Not re-checked here:**
  - issue #239, the PR-only explanation for `pr_agent_loop_invalid`;
  - specs PR #391, the Claude Skill feedback contract;
  - validating the refreshed example graphs against real user stories;
  - assessing the public-source discovery budget refusal.
- **Recommendation:** keep the chronology off develop, but confirm these items are tracked on issues.

**nonpython-shared-skills-github-documentation-3-S1: broken table in the operations interface README**
- **Category:** README structure. Applies to the docs and how they render.
- **Detail:** in `skills/interface/operations/README.md`, prose at `:10-27` was inserted after the first table row (`:8`). The rows for `SkillOperationServer`, the handler, `Settings` and `main` (`:28-31`) are now detached from their header and will not render as a table.
- **Origin:** this came from later manual-editor work, not from dropped PR238 content. I'm listing it as a suggestion.

## Settled background (not reopened)

- `GitTreeEntry` → `SkillRepositoryEntry`.
- The `_NoRedirect` alias was retired.
- The `retained.py` migration.
- documentation-1 Q1 (structured-data and node-http docs retired).

## Leftovers / UNVERIFIED

- Whether the GitHub interface READMEs document the Issue/PR caps and the allowlist difference (affects Q1).
- Whether `specs/AGENTS.md` carries the rules on issue-edit approval and closing keywords (affects D1).
- Whether issues #239 and specs PR #391 are still open (affects Q2).