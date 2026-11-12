# Generic-imports packet (frozen d3d06e3a) and C-01 correction delta

**Bottom line:** I found no confirmed defects in the parts I read. The generic import and ownership changes keep dynamic auth, mediation authority and confirmation, WorkGraph grant identity and symbol owners as they were. Some lazy imports are now loaded eagerly at module start, which changes import side effects; that is a question below, not a defect. C-01 is resolved for missing anchors. This is not a PR, merge or issue-closure approval.

This is the same session. The earlier rate-limited turn had already read `imports.diff` lines 1–3699. I didn't reread those; I continued from line 3700.

## Coverage

**`imports.diff`, read line by line:**
- lines 1–3699: git credential helper, workflows, `host/http`, GitHub interface, transports, PR contract and models, the token move, `host_services`, leases, mediation (`authority`, `cli`, `service`, `store`, `utils`), publication (bundle, `cli`, `controller`, handoff store, verified, `verifier`), deletion of `laomedo/http`, Skills READMEs and interface clients, `operations/manual.py`, and the start of the `operations/models.py` deletion;
- lines 4725–4830: `operations/service.py`, `operations/settings.py`, `utils/__init__.py`, `utils/proposal.py`;
- lines 5612–6592 (end): `skills/settings.py`, `skills/sources/*`, and all of `work_graph/*`.

**`imports.diff`, file headers only, not read line by line:**
- lines 3700–4724: the rest of the `operations/models.py` deletion, plus the new `models/history.py`, `models/manual.py`, `models/proposal.py`, `models/provenance.py`;
- lines 4830–5611: `utils/summary.py`, plus registry `README`, `errors`, `models`, `settings`, `store` and `utils/{diff,files,hashing,inspection,paths,policy}`.

I did check that the moved symbols' callers in `service.py`, `manual.py` and `sources/*` import from the new defining modules.

**Source context read:** siwc lazy-import sites (via grep), `stage_adapter.py` imports, and globs confirming that `git/credentials/`, `github/workflows/`, `http/` and `host/credentials/token/` no longer exist.

**Not read:** `imports-paths.json`, `imports-ast-inventory.json`, `imports-combined.diff`, `integration-findings.md`, the C-01 logs, and `c01-pinned-output.json`.

**C-01:** I read `c01-correction.diff` in full. The frozen worktree is still at d3, so for the pre-correction state I used a grep of the installer's write and copy calls.

## Confirmed findings

None.

## Questions

**Q-I1 (low): lazy imports are now loaded at module start, changing import side effects.** Three places that used to import inside a function now import at the top of the module:
- `host/managed_service.py:1595-1596` loads both `host_services.main` and `publication.cli.main` whichever service is selected. That transitively loads the mediation store, GitHub transports, `truststore` and the verifier.
- `host/mediation/cli.py` loads `mediation.service` at the top.
- `work_graph/launch.py:6283-6286` loads `stage_adapter`, `docker_stage` and `github`. `grants.py` imports `launch`, so even `python -m laomedo.work_graph inspect` now loads them.

The effect: an import failure in one service's dependencies now stops the other service, or the read-only commands, from starting. Behaviour once running doesn't change:
- `stage_adapter.py:10-16` imports only the standard library and `work_graph.runs`, so this needs no optional graph framework;
- I found no import cycle (`launch` doesn't import `grants`; `utils` still imports siwc `connection` lazily);
- the installed-wheel core-import checks pass.

Optional hardening: restore the per-branch lazy import in `managed_service` and in `cli.py`.

**Q-I2 (low): is `truststore` a core dependency?** `transport/rest/transport.py:584` imports `truststore` at module top. That change came with upstream develop. I did not read `pyproject.toml`; the passing wheel tests suggest it is declared.

## What the read portions preserve

- **Dynamic credentials:**
  - `HostTokenConnection.current` still rereads the token file on every call;
  - callers still pass the bound method `connection.token` and `connection.current`, never a captured value;
  - the siwc default arguments (`exchange`, `verify`, `refresh`, `revoke`) were already fixed when the function was defined, so switching from the module alias to a direct name changes nothing (test monkeypatching of the module attribute never affected them).
- **Lazy-import cycles:** the siwc `connection` lazy imports remain in `utils`, `cli` and `browser`, and `browser`'s `TYPE_CHECKING` block is intact.
- **Mediation and publication:** these are pure name rewrites. `MediationError` and `KnownRejected` are the same classes from `mediation/errors.py`. The order of grant checks, effect journaling, retry approval and handoff checks is unchanged. `_validate_effect` still imports the Issue `validate_patch` lazily; the PR one is now aliased as `validate_pr_patch`, with no name collision.
- **WorkGraph:**
  - `_host_principal()` is still evaluated on every issue and redeem;
  - grant binding still checks `work_key`, `content_digest`, runner, scope, limits and expiry;
  - the CLI confirmation prompt and arguments are unchanged.
- **Moves:** git helper → `git/credential_helper.py` (standard library only, still GitHub-only, still reads the token from the environment at call time); workflows → `github/workflows.py`; `NoRedirect` → `host/http.py`; token → `credentials/token.py`. No old package directory is left behind to shadow the new modules.
- **Owners:** `skills/settings.py` is a deliberate central entry point. It re-exports the original objects and creates no settings instances. Maintained callers in `service.py`, `manual.py` and `sources/*` import from the defining modules, not from that entry point.

## Questions carried over from core packet 3

| ID | Disposition |
|---|---|
| Q-P1 | **Closed, optional hardening.** It is not a defect and was not introduced by this merge. If the profile-mode request fails, the session falls back to ordinary mode and no change broadcast is sent; ordinary logout still works. Private-profile revocation remains gated by #259; this does not approve private access. |
| Q-P2 | **Closed on the mechanism you traced, not independently verified.** I did not read the deployed multiselect. If the effect sets only local state, a child re-render cannot change the parent's `options` reference, so no loop. |
| Q-P3 | **Closed.** There is no supported module-import contract for that file. |
| Q-P4 | **Closed.** Pre-existing in develop and display-only. |
| Q-P5 | **Closed as an accepted residual.** I did not verify the pinned upstream user creation. Even if the name came back different, the result fails safe: the user is told to check the list, and creation is never retried. |

## C-01 disposition: resolved for missing anchors

- In `c01-correction.diff`, every in-place write (header, logout, auth context, password gate, general page, empty page) is moved to one loop after `shutil.copytree`.
- `copytree` itself runs only after all eight anchors have passed validation. A missing anchor therefore exits with no files written and no profile assets copied.
- The new test covers the four late anchors, checks that every file is byte-identical afterwards and that no `laomedoProfiles` folder appears, and calls the declared function through `run_path` (no module alias).
- There is still no transaction for I/O failures partway through the write loop, or for the outer overlay as a whole. As you disclosed, that is not claimed.
- I did not read the C-01 logs or `c01-pinned-output.json`, so the claim that the 17 output files are byte-identical rests on your evidence, not on my reading.

D-01 and D-02 were not re-reviewed, as instructed.

## Verdicts (this packet only)

- **Code:** No blocking defect in the parts I read. Q-I1 and Q-I2 are optional. Skills registry/operations lines 3700–4724 and 4830–5611 were read by header only and are not covered by this verdict.
- **C-01:** Resolved.
- **Visual:** No change since the previous approval.
- **Still pending:** the tests/maps/docs packet, the combined-diff and inventory artifacts, and real owner-graph acceptance. Reviewer status for those: not reviewed, reviewer pending. No merge or issue closure is authorized.