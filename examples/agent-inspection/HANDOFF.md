# Agent inspection implementation handoff

## Branches and review links

- Product: `feat/164-langflow-demo`, [Laomedo PR #168](https://github.com/amadou-6e/laomedo/pull/168), target `develop`.
- Specs: `docs/378`, [specs PR #379](https://github.com/amadou-6e/specs/pull/379), target `main`.
- Product issue [#167](https://github.com/amadou-6e/laomedo/issues/167); specs issue [#378](https://github.com/amadou-6e/specs/issues/378).
- Reviewed implementation: `00a9b98c89c28ca12bc5f83eafb27832ac20a768`. Reviewed spec `ce59be6`; final spec `8020cc8` adds only the already-reviewed `incomplete` diagram state.
- This handoff commit adds documentation and activation drafts; it does not activate or alter the reviewed product code.

## Implemented

Codex toolbar Inspect agent, Overview, Output validation and metadata-only Timeline. Authenticated bounded runner reads, exact loopback proxy allowlist, existing backend transport secret. Requested/reported model and effort are separate; missing usage is unknown. Explicit history selection is not attested as this node's invocation. Raw text, commands, arguments, reasoning and tool results are withheld. See the spec for bounds and limits.

This branch also contains previously reviewed native Prompt Template and GitHub Issue Operation-input work, plus previously reviewed Issue viewer layout changes. Preserve customized writer-node code; do not click catalog Update All.

## Checks completed

- Final frontend production build passed in a separate output directory.
- Projection/native-example: 12 tests, one Windows unprivileged-symlink skip.
- FastAPI authentication/error/no-cache: 3 tests passed in pinned Langflow image with no network.
- Focused runner/handoff/inspection regression: 70 tests, one skip.
- Browser check passed: exact Codex toolbar, explicit history, invalid JSON rejection, timeline sequence zero, keyboard tabs, read-only refresh; zero dispatches.
- Specs validation: 0 errors, one existing large Draw.io warning. Four workshop pages visually inspected using temporary renders; no exports committed.
- Initial full host suite: 731 tests, two failures, 16 skips. Stale native-example code pin fixed. Existing Windows file-lock failure passed focused rerun. Final whole-suite rerun was still running at handoff; retrieve its result before claiming full-suite success.

Run log on this machine: `claude-review.local/agent-inspection-final-host-tests.log`. It is ignored and not shipped. Do not publish raw logs without inspecting content.

## Review and approval

Claude approved the source/spec and the corrected activation package. [REVIEW.md](REVIEW.md) preserves conclusions and limits. Owner preapproved necessary work/configuration for this implementation and requested remote updates before permission checkpoints. No model turn or GitHub issue/publication write was used for inspection.

## Activation is NOT done

Running viewer7864 still mounts the previous source/frontend; dedicated runner8784 still runs the old source and lacks inspection endpoints. A browser test used intercepted responses and new assets, not actual activation. Do not tell the owner the live inspector is ready yet.

Prepared drafts: [controller upgrade](upgrade-controller.draft.ps1), [viewer swap](activate-viewer.draft.py), [deployment scope](DEPLOYMENT.md). These are machine-specific drafts, not portable installers. Revalidate paths, exact process identities, lease PID and asset/source manifest before running.

Remaining reviewer recommendations before activation:

1. Add an exact reviewed-source revision check in the controller draft before stopping anything. A documentation-only descendant is acceptable only after confirming unchanged executable diff; do not treat arbitrary HEAD as reviewed.
2. Verify independent lease-service identity/aliveness before stopping the controller as well as afterwards. PID39780 was the observation, not a durable identifier. Preserve the service.
3. Document or implement controller rollback if new startup fails. Viewer rollback exists; controller startup failure currently leaves the service unavailable safely.
4. Fix stale viewer-script comment and success field `catalog_preserved_plus_github_issue` to say catalog is preserved exactly. No catalog installation is authorized by this draft.
5. Generate the missing final build manifest (asset hashes + exact source revision) after checks; viewer activation refuses without it. Assets live at `claude-review.local/agent-inspection-build`, outside Git. Rebuild elsewhere if absent.

Then upgrade only dedicated8784/8785, preserving all campaign hashes and ledger; swap viewer after all guards pass; verify real recorded evidence through the inspector and refresh. Keep standing8779/8780/8782/8783 untouched.

## Campaign and exact verification target

- Existing flow: http://127.0.0.1:7864/flow/065ae0e0-13eb-458e-902c-6a245a289278
- Recorded run: `7433da21-1389-428a-b43b-75834fa57d99`.
- Current campaign state: `C:/Users/amado/AppData/Local/Temp/laomedo-issue-operation-input-20261013-a`; runner subdirectory. Ledger observed 1/3, two remaining. Never reset it.
- Controller PID40332, independent lease PID39780 were observations; confirm actual identities.
- Expected evidence: execution completed, strict final JSON rejected (`extra_data`, line1/column394), Contract rejected, no issue-effect receipts. Recheck current state before activation.
- Inspector connection: only `http://host.docker.internal:8784`; backend transport file is already mounted. Never read/print provider login or transport token values.
- No Run click, no model probe, no GitHub write is needed to finish this slice.

## Finish

Read applicable AGENTS.md and reviewer skill; preserve one bound reviewer session for the current Codex conversation. Retrieve final test result and CI, resolve failures honestly, complete activation/readback, update PR evidence and checklists. Merge specs #379 before implementation #168 when reviewed final checks pass. Issues remain unchanged; do not close them without the applicable explicit approval.
