# nonpython-runtime-build: COMPLETE

All 37 entries are classified. Docker image builds and container runtime stay **UNVERIFIED** because they can't be exercised read-only. This is conservation scope only: all 23 PRs remain **HOLD**, and provider, browser and owner gates are separate.

Current evidence comes from the frozen Agent250 tree (`.tools/conservation-review-20261106/agent`), which owns all of these paths. I read the root and owner `AGENTS.md` files. Agent250 has no `CLAUDE.md` (the exact Read failed).

## What I read

**Packet lines read:** 1-124, 1703-1764, 2322-2361, 2468-2484, 2485-2610, 4098-4122 and 4571-5073. I read the index in full.

**Not read** (all exact-blob entries; I assessed these from their current consumers instead):
- 125-1702: body of the `docker/claude` lock file;
- 1765-2321: the TypeScript sources and `native-events.patch`;
- 2362-2467: the rest of the `codex-acp` lock file;
- 2611-4097: the seccomp policy and licence bodies;
- 4123-4570: the `.mjs` bodies.

**Missing input:** `dependency-manifest-consistency.json` is not under `resume-20261106/nonpython/`. I used the copy at `resume-20261106/dependency-manifest-consistency.json`: npm manifest roots match their locks, uv has 42 package records and no unresolved names.

## Disposition by entry

| PR / path | Disposition | Current evidence |
|---|---|---|
| 213 `work-graph.yml` (list of runner-gated tests) | **GAP** | See D2. The tests that don't need the `runner` extra run in ordinary discovery (`work-graph.yml:24-29`). The ones that need `acp`/`py_docker` don't run anywhere. |
| 214 `work-graph.yml` (`test_acp*`, `test_codex_acp_controller`) | **GAP** | D2 |
| 227 `work-graph.yml` (`test_runtime_failure*`) | **GAP** (the `py_docker`-dependent parts) | D2. The `py_docker` imports are conditional at `test_failure_observations.py:16`. |
| 226 `work-graph.yml` (EXP-08 retained runner) | **INTENTIONALLY_SUPERSEDED** | Covered by ordinary discovery of `tests/test_skills/test_workspace` (Agent `tests/README.md:104-107`). |
| 213, 214, 227 `pyproject.toml` / `uv.lock` (py-docker pin `c0d92a7`, then `+agent-client-protocol==0.12.1`) | **PRESERVED**; the old pin is superseded by `49652f4` | `pyproject.toml:19-23`. The current `uv.lock` blob is byte-identical to PR 225's. |
| 225 `pyproject.toml` / `uv.lock` (py-docker `49652f4`, pywin32 on win32) | **PRESERVED** (exact blobs) | `pyproject.toml:20-22`. The consistency JSON reports no unresolved names. CI installs with pip, so it never consumes the lock (S1). |
| 216 `pyproject.toml` package-data | **PRESERVED** | `pyproject.toml:47-51`. `test_packages.py:79-104` checks installed resource bytes and their owners (`agents/agents/codex/resources`, `host/mediation/resources`). |
| 221 `python-format.yml` | **PRESERVED** (path updated) | `python-format.yml:16-21`. `tests/test_shared/test_formatting/test_policy.py` exists. |
| 221 `pyproject.toml` / `uv.lock` (Black) | **PRESERVED** | `pyproject.toml:18,26-38`. `docs/architecture/python-formatting.md` exists. The lock carries the `dev` extra. |
| 214 `.gitattributes` (`docker/codex-acp/** eol=lf`, patch whitespace rule) | **GAP** | D1 |
| 216 `.gitattributes` (seccomp path move) | **PRESERVED** | `.gitattributes:4`; `test_docker_preflight.py:74-80` asserts it. |
| 216 `.gitattributes` (seven `-text` rules for immutable exports) | Six are **INTENTIONALLY_SUPERSEDED**; one is a **GAP** | The six target files no longer exist in Agent250. `examples/skill-summary/executed-flow.json` still exists but lost its rule → D3. |
| 238 `.gitattributes` (`-text` for the `skills-direct-import-errors` contract) | **INTENTIONALLY_SUPERSEDED** | That inventory was retired (tests-5 G16). |
| 214 `docker/claude/Dockerfile`, `package.json`, `package-lock.json` (exact) | **PRESERVED**; build is **UNVERIFIED** | The consumer path `/opt/acp/node_modules/.bin/claude-agent-acp` is at `claude/agent.py:517`, matching `npm ci --prefix /opt/acp`. The image tag `…-acp0.98.0` (`claude/settings.py:5`) matches the pin in `package.json`. `command_mcp.py` is present. |
| 214 `docker/codex-acp/Dockerfile`, TypeScript, patch, `package.json`, `package-lock.json` (exact) | **PRESERVED**; build is **UNVERIFIED** | Python consumes `/opt/acp/index.mjs` (`codex/controller/models.py:217`). The image tag and ID are pinned at `codex/settings.py:6,9`, matching README lines 6 and 46. The lock pins `@openai/codex` 0.159.2 by integrity hash, and the Dockerfile checks `codex --version`. Vitest only runs during `docker build` (S3, which predates these PRs). |
| 214 `docker/codex-git/Dockerfile` deleted | **INTENTIONALLY_SUPERSEDED** | Its absence is asserted at `test_protocol/test_boundaries.py:35`. `GIT_IMAGE = IMAGE` (`codex/settings.py:12-15`), and the ACP image installs git (Dockerfile line 1746). |
| 216 R100 `codex-seccomp.json` | **PRESERVED** | `SECCOMP` and its SHA-256 are pinned at `codex/settings.py:46-51`. A changed profile is refused (`test_sandbox.py:158`). The LF rule is tested. |
| 216 R100 `runner-config.toml` | **PRESERVED** | `CONFIG` with hashes for both CRLF and LF checkouts at `codex/settings.py:41-43,59-62`. I read the content (lines 4106-4115): `auth.json` is denied and the network is disabled. |
| 216 R100 `agent_mediation_client.mjs`, `agent_gh_adapter.mjs`, `agent_git_remote.mjs` | **PRESERVED** | `MEDIATION_CLIENT` at `codex/settings.py:54-56`. Installed bytes and parent folder are asserted at `test_packages.py:87-90,104`. |
| 216 R100 `moby-profiles-LICENSE` | **PRESERVED** (packaging glob only) | Included by `"resources/*LICENSE"` at `pyproject.toml:49`. No explicit test (S2). |

## Findings

**nonpython-runtime-build-D1 — defect, medium. Owner: Agent250.**
- **What was lost:** PR 214 added two `.gitattributes` rules, still present in PR 216 (packet lines 2577-2578):
  - `docker/codex-acp/** text eol=lf`
  - `native-events.patch whitespace=-blank-at-eol`

  Agent250's `.gitattributes` (lines 1-22) has neither. There is no nested `.gitattributes`, and no test guards these rules; the only test checks the seccomp rule.
- **Mechanism:**
  1. On a Windows checkout with `core.autocrlf=true`, the patch and TypeScript files arrive with CRLF line endings.
  2. The Dockerfile then runs `git apply /tmp/native-events.patch` against the upstream adapter's LF sources and records checksums of the patch and extension (Dockerfile lines 1741-1743).
  3. The README tells users to build from this directory (line 6), and this user works on Windows.
- **Uncertainty:** it depends on the git configuration. I did not run a build.

**nonpython-runtime-build-D2 — defect, medium. Owner: Agent250 CI. It escalates T2-S3 with CI evidence.**
- **Old CI:** PRs 213, 214 and 227 ran the ACP, controller, runtime-failure and provider tests with `.[runner]` installed.
- **Current CI:**
  - `work-graph.yml:11-13` installs `.[runner]` but runs only `test_docker_preflight.py`.
  - `package-and-test` (`:24-29`) installs the wheel without extras.
  - So these tests skip in every CI job:
    - `test_acp_controller.py:20`;
    - `test_protocol/test_session.py:11-19`;
    - `test_protocol/test_provider_bindings.py:20`;
    - `test_claude/test_session.py:50`;
    - `test_claude/test_login_session.py:193`.
  - Only two workflows exist.
- **Effect:** the ACP cancellation and terminal-outcome controls behind the settled T1-D1 and T1-D2R findings never run in CI.

**nonpython-runtime-build-D3 — defect, low. Owner: Agent250.**
- **What was lost:** `examples/skill-summary/executed-flow.json -text` (PR 216, packet line 2591) was dropped, but the export still exists in Agent250.
- **Effect:** line-ending conversion on checkout can now change the immutable bytes. No test reads the file.
- **Fix, either of:**
  - restore the rule;
  - or archive the export to `exp`.

**nonpython-runtime-build-Q1 — question. This is about docs, not implementation.**
- **The problem:** `docker/codex-acp/README.md` mixes historical provenance into active docs:
  - lines 3-4: "selected … on draft PR #214; unreleased and not accepted";
  - lines 35-49: the probe narrative.
- **Why it matters:** this conflicts with the requirement for declarative architecture READMEs.
- **The question:** should that history move to `exp` or a provenance doc?
- **Not checked:** `docker/claude/README.md`.

**Optional suggestions (not dropped assertions):**
- **S1:** CI resolves with pip, so `uv.lock` is never consumed and transitive dependencies are unpinned. This predates these PRs.
- **S2:** add `moby-profiles-LICENSE` to the explicit list of installed resources.
- **S3:** the image builds and Vitest suites aren't in CI. This was already so at PR 214.

**Applicability:** D1 and D2 are implementation and CI. D3 is an example artefact. Q1 is docs or spec. Nothing in this packet is visual.

## Remaining gaps

- Docker image builds, container runtime and provider behaviour remain **UNVERIFIED**.
- The exact-blob bodies listed above were not read.
- Everything from earlier packets carries forward: tests T1–T5 and runtime C4–C6.