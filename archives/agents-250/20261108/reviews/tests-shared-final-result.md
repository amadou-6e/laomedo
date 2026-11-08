I've read the whole shared test packet. **Verdict for this packet: no confirmed defects.** It's moves, campaign-wrapper retirements and new internal controls, and every guard I checked was either kept or moved to a named replacement. Q-P2 and Q-P3 now have source/test evidence (below). This is not approval of the PR, merging, or retiring the old PRs.

## Ranges read
- **`E/test-own-shared.diff`:** lines 1–7404 in full, in pages of 750–1000 lines (1–750, 751–1550, 1551–2450, 2451–3350, 3351–4250, 4251–5250, 5251–6250, 6251–7250, 7251–7404).
- **`E/test-support-final-source.txt`:** lines 1–168 (all of it).
- **`E/remaining-base-disposition.txt`:** lines 1–13 (all of it).
- **Narrow current-source checks:**
  - `tests/test_agents/test_codex/test_sandbox.py` lines 20–59
  - searches for the guard codes across `tests/` and `src/`
  - search for duplicate class names

## Confirmed defects
None.

## Questions
1. **Q-S1: the diff is labelled with an older head (low).** Line 1 says "head 2e2be4c6…", not `e27f1c92`. If the shared tests changed between those commits, this packet doesn't cover that change. Please confirm the own-diff between `2e2be4c6` and `e27f1c92` under `tests/` (excluding provider tests) is empty.
2. **Q-S2: the disposition file is incomplete (low).** `remaining-base-disposition.txt` only lists `command_mcp.py` and `RunnerRecovery.tsx` as zero own-diff. The "Publication and Skill registry own diff" heading at line 13 has nothing under it. Your classification of `publication/handoff.py` and `store.py` is plausible, and nothing in this packet contradicts it. But this file doesn't prove it.
   - One concrete interaction did change: `test_rejected_old_handoff_does_not_block_new_run_on_same_branch` (3477–3490) is a new test against `MediationStore` publication handoffs.
   - If the store source has zero own-diff, the test pins existing behaviour, which is fine. Otherwise it is new behaviour that hasn't been reviewed.

## Suggestions (non-blocking)
- **Duplicate suite.** `WorkspaceSkillGitTests` now exists twice: in the new `tests/test_agents/test_workspace/test_skill_exclusion.py` (742–993) and the updated `tests/test_skills/test_workspace/test_exclusion.py`. The bodies are essentially the same; one imports `FakeServer` from `test_lifecycle`, the other from `transport`. Keep one.
- **Optional dependency at import.** `test_examples/handoffs.py` imports `lfx` with no guard and runs `examples/graph.py` when imported. That's fine while only skip-guarded tests import it.
- **Experiment data still read by base tests.** These are unchanged base dependencies, not new ones:
  - `test_timeout_trace.py` reads `experiments/exp65/observation.json`.
  - `test_work_graph_launch.py` reads `experiments/exp16/corpus.json`.

  The retired `test_exp100_handoff_s3` wrapper, which ran `experiments.*` through a subprocess, is gone, so this packet adds no new CI dependency on `exp`.

## What was preserved or moved
- **Container lease (`test_container_lease.py`, deleted):**
  - Ownership and cleanup semantics are now tested through the real `py_docker.ContainerWatch` in `test_host/test_leases/test_cleanup.py` (2307–2412). It covers delayed creation removed by immutable ID, `late_owned`, `never_observed`, `absent`, an unconfirmed final inspection never reporting removed, and foreign containers never being removed or given an invented ID.
  - The `supervise`-on-EOF and detached-process tests moved to `test_supervision.py`.
  - The new "missing legacy endpoint cannot claim absence" test (522–527) is stricter than before.
  - Only the Docker CLI stderr-casing test is gone, and the CLI path is gone with it.
- **Sandbox policy (`test_runner_sandbox_policy.py`, deleted):** each guard has a replacement:
  - `seccomp_profile_changed`: `test_codex/test_sandbox.py:158`
  - `docker_image_digest_changed`: `test_sandbox.py:229`, `test_docker_preflight.py:112,176`
  - `invalid_local_image_id` (all three variants): `test_sandbox.py:264–277`
  - the split token kept out of the control environment: `test_sandbox.py:21–58`
- **Other deleted Agent tests:**
  - `test_opencode_boundary.py` and `test_opencode_events.py` → the ACP OpenCode boundary/capture tests reviewed in the provider packet.
  - `test_model_catalog.py` → `test_codex/test_model_catalog` (provider packet).
- **Campaign wrappers (exp19/100/104/139, paired, persistent, native-*, live-*):** all deleted, consistent with the campaign-only classification you'd already approved. I'm not turning any of them into production requirements.
  - The two exp139 hooks inside publication tests (`test_stage.py`, `load_retained_shared`) were removed cleanly.
  - `support/retained.py` widens symbol remapping to `laomedo.agents.*` and `laomedo.activity.*`.
- **New guards (internal controls):**
  - Lease HTTP wire order and redaction (2418–2647).
  - Grant-book windows and audit records.
  - Lease-loss and refused-lease cleanup journals that never leak callback secrets (2985–3107).
  - Mediation lifecycle: approve → bind → read → done → revoke (3243–3349).
  - Strict private-directory permissions.
  - Proxy and redirect refusal for mediation, Langflow login and mediator health (7062–7187).
  - Ingestion inode-swap refusal.
  - Verified-stage refusal of divergent history, agent hooks and hostile remotes.
  - Runner HTTP keeps the registry error categories.
- **Mock targets** follow the move, patching where each name is used: `host.leases.service.*`, `host.leases.client._write_json`, `integrations.langflow.feedback.pr.agent_operation`, `OpenerDirector.open`. I found no wrong targets.
- **Shared infrastructure lifetime:**
  - `RunningHTTPServer` always closes the socket and joins its thread, and raises if the thread is still alive.
  - `RunnerCase` closes every owned resource through an `ExitStack`, including when setup fails part-way.
  - `test_cleanup` patches `py_docker.Client`, so the endpoint selection it checks is internal only.
- **Skips:** all gate on `py_docker`, `lfx`, Windows, git or `gh`, which match the declared extras. The new `test_host/test_runner/__init__.py` and the moved `test_work_graph/*` files keep test discovery working.

## Q-P2 and Q-P3 dispositions
- **Q-P2 (split selection and revocation): partly resolved.**
  - **Selection:** the Python guard `executor_selection_mismatch` no longer exists anywhere in `src/` (searched). Selection is now enforced in the TS extension, which rejects an unregistered split `environmentId` (`LaomedoExtension.test.ts:38`). I found no test for an ambiguous or wrong `cwd`; this stays a gap.
  - **Revocation:** `auth_revoked_during_turn` is raised at `controller/service.py:339`, tested at `test_acp_controller.py:238`, and its outcome is tested in `test_lifecycle.py:873–1006`.
  - All of this is unit-level. Live split acceptance still hasn't been retested.
- **Q-P3 (environment serialization): resolved at the internal-control level.** `test_sandbox.py:47–55` asserts:
  - `ACCESS_TOKEN` exists only as a `SecretStr` in the container spec;
  - it is absent from the Docker client environment;
  - it does not appear in `LAOMEDO_CODEX_ARGS`.

  Spec dumps are also checked for secrets (provider packet, 7593 and 7849). Together these replace the retired `DockerSelection` test.

## Remaining gaps
- Q-S1, Q-S2 and the `cwd`/ambiguity part of Q-P2.
- Q-P1, wire coverage for an output precheck arriving while a prompt is pending (under implementer investigation).
- The fixture/source packet (8,792 lines) hasn't been reviewed yet, and the integration verdict comes after it.
- **No acceptance yet:** this packet is internal controls throughout. Still not retested:
  - native GitHub mediation (#215);
  - default Console and app-owned OAuth;
  - the split executor;
  - a new child capture;
  - Docker being down or uninstalled.
- Still open:
  - TypeScript is inherited red (259 vs 265).
  - Spec 403 is still a draft.
  - The owner's graph validation is missing.
  - The 23 old PRs stay on HOLD, with no merge.