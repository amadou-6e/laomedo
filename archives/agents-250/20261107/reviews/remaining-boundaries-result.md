# PR250 shared-boundary source packet: final review (runtime matches reviewed `6018390e`, head `bb8fa8ca`)

I found no confirmed defect in these files, so the scope verdict is **APPROVE**. There are three low-severity questions, mostly about raw error text reaching HTTP responses, and three optional suggestions. I did not have the base (`bb250135`) versions of these files, so every "carried" label below is inferred from the packet saying the code was moved, not from comparing old and new.

## Coverage

- **`remaining-shared-boundaries.txt`:** read lines 1–2001, which is the end of the file. Page 1–500 ends inside `cleanup.py`, and page 1501–2000 ends at `git/windows/tree.py` line 170.
- **`agent-readmes-current.txt`:** read lines 1050–1114, which is the real end. The workspaces README's last table rows and closing text are at 1050–1062, and the full `workspaces/skills/README.md` is at 1064–1114. Together with my earlier read of 1–1054, I have now read the whole file. My earlier "30 READMEs, 1,054 lines" count was a cut-off read, not the true length.
- **Not read:** the `HASH` constant in `artifacts/settings.py`; `workspaces/settings.py` (the `_SHA` pattern and size limits); `MAX_BODY`, `_id` and `_read` in `base/utils.py`; the `read_feed` limit; `startup_gate`; the Git runner, repository and worktree code; `is_link`, `inventory` and `tree_hash` in the Skills registry; all the error classes; any test files.

## Questions (low)

**A-SB-Q1 · error text in runner HTTP replies** (`host/runner/http/handler.py:155-162` and `:245-256`)
- **Trigger:**
  - a GET request that fails with an `OSError`, a bad `after`/`limit` value (`ValueError` from `int()`), or a damaged attempt JSON file;
  - a POST with a non-numeric `Content-Length` (`:42`), a missing body key such as `task` or `paths` (`KeyError`), or JSON that won't parse.
- **Mechanism:** the reply sets `error_category` to `str(exc)`, the raw exception text.
- **Consequence:** the reply can contain an absolute host path from `OSError`, the supplied header value, or a JSON parser message. These are not credentials, and only a caller who already holds the token sees them. But it breaks the stable-error-code contract and the redaction you asked me to check. The same handler also turns a GET `ValueError` or `OSError` into a 404.
- **Origin:** probably carried.
- **Question:** were these replies byte-for-byte the same at base? If so, leave this outside the refactor's scope.

**A-SB-Q2 · cancel arriving during startup** (`host/runner/http/server.py:36-41`)
- **Trigger:** a `.cancel` file appears after the check at `:37` but before `listening.touch()` at `:41`.
- **Mechanism:** nothing checks for `.cancel` again after the socket binds.
- **Consequence:** the server reports itself as listening even though a cancel was requested. This only matters if `startup_gate`, which I did not read, or the parent process doesn't settle it. The docstring says cancellation is reconciled "before readiness is published". The code shown proves that only for a cancel that arrived before the check.
- **Origin:** probably carried.
- This has nothing to do with the main-preview recovery failure, whose cause is still unknown.

**A-SB-Q3 · missing resume key escapes as `KeyError`** (`agents/orchestration/utils.py:105-116`)
- **Trigger:** a resume source that has `thread_id`, `post_run_hash` and `run_id`, but no `model` or `effort` key.
- **Mechanism:** `source[k]` raises `KeyError`, not `HandoffError`.
- **Consequence:** the caller gets an unstable error instead of a stable refusal code. Also, `envelope` returns `to_payload()` (a dict), not the `AgentHandoff` model, so the result is a dict, as before.
- **Origin:** probably carried.

## Optional suggestions

- **A-SB-S1** (`artifacts/utils.py:109-119`): the parent check `p.exists() and not p.is_dir()` accepts a symlinked directory. The target workspace only comes from preparation that rejects links (`_hash_tree` and Git mode `120000`), so it is confined in practice. A direct link check would make the confinement explicit. Also, if writing fails partway, earlier writes stay in place; this is probably carried.
- **A-SB-S2** (`workspaces/utils.py:46`): in non-Git mode, `_hash_tree` reads every file into memory with no limit (the byte and entry limits apply only when `exclude_root_git` is set). Probably carried.
- **A-SB-S3** (`workspaces/cleanup.py:33`): `shutil.rmtree(onerror=…)` is deprecated from Python 3.12. It still works.

## Checked and found sound

- **Pydantic models:** all of them are strict, frozen, refuse extra fields and hide input in errors. The one exception is `WorkspaceSnapshot` (`workspaces/models.py:28`), which leaves out `hide_input_in_errors`; it holds only hash strings, so nothing sensitive would show.
- **Omission and nulls:**
  - `ActivityAttemptRecord.to_record` leaves out `fresh_thread` when it was never set, while the end fields with no default always serialise as explicit null.
  - The Claude field order is kept.
  - `ActivityProjection` emits `diagnostics` only when it was set, in both wire orders.
  - `HandoffTarget` leaves out keys that were never supplied, and `source`/`prior` are always explicit null when absent.
- **No credentials in public output:**
  - `ActivityInvocation.store` is hidden from repr.
  - The private-state policy and result fields and the `WorkspacePaths` fields are excluded from repr and from serialisation.
  - The artifact path filter blocks dotfiles, auth, credential and session files, keys and `raw-events.jsonl`.
- **Windows ACLs:**
  - Only a newly created leaf directory is restricted.
  - Ownership is checked before the DACL is replaced.
  - The DACL is protected, with one inheritable full-control entry for the owner, and the code never takes ownership.
  - `verify` requires every entry to be allow-type, inheritable both ways, not inherit-only or no-propagate, full access, and the owner's SID. Operator precedence in these bit tests is correct.
  - UNC paths and paths with `..` are refused.
  - Every ancestor is checked for links, reparse points and `.git`, before and after creation.
  - On POSIX the owner must match and the mode must be `0o700`.
  - Subprocesses use a filtered environment and a deadline clamped to the time remaining.
- **Request limits and auth:**
  - Every request checks the bearer token with `compare_digest`.
  - POST requires the JSON content type and a body length between 1 and `MAX_BODY`.
  - The async route sets its response gate in `finally`, after the reply is sent.
  - Publish requires an empty body.
  - Loopback addresses only.
- **Workspace confinement:**
  - Cleanup refuses the state root itself, anything outside it and links. Its read-only retry stays inside the tree and skips links.
  - Git preparation refuses the following, then cleans up a partial clone or reports `git_workspace_cleanup_unverified`:
    - submodules, symlinks, tracked skill paths, sparse checkouts, a dirty source tree;
    - any HEAD or remote mismatch after the clone.
  - The baseline repository uses an isolated home, no templates, hooks pointed at that home, and no signing.
- **Windows process tree:**
  - A process tree can have only one root, assigned while suspended.
  - Exactly one primary thread must be found, it must still belong to that process, and it must resume from a single suspend count.
  - Kill-on-close is a backstop only: cleanup counts as confirmed only when the job reports zero active processes.

## Verdict

**APPROVE** for this shared-boundary source scope. A-SB-Q1 to Q3 are open questions, not blockers. This is not approval of the whole PR, the spec or a merge.

These still stand:
- the main-preview recovery failure has no established cause;
- issues #203 and #215;
- the paths not retested: Console/app-owned OAuth, the split executor, child capture, Docker down or uninstalled;
- the TypeScript baseline is still red (259 vs 265);
- spec 403 is still a draft;
- your final graph approval is still needed; PR250 stays a draft and the old PRs stay on hold.