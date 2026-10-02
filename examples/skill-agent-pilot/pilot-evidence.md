# Pilot evidence, issues #8 to #11

The Langflow-to-Codex pilot was executed on 2026-10-01 with an explicitly
authorized four-turn cap and the existing private Docker credential volume.
No new Codex auth copy was made. [e2e-results.json](e2e-results.json) records
sanitized identifiers, hashes, and checks. Raw Langflow responses and native
events remain outside Git. A missing observation is not a pass.

| Claim | Evidence | Result |
| --- | --- | --- |
| Existing Docker route can initialize Codex without a model turn | `--preflight` against pinned image and existing private volume returned model/effort list, `submitted_turns: 0` | Pass |
| Existing grant allows draft write and denies protected paths | Real app-server `command/exec` canaries returned workspace write exit 0, canonical and sibling store write exit 2, auth read exit 1; both sentinels unchanged | Pass for tested paths |
| Docker image, CLI, and permission file pinned | Image ID, `codex-cli 0.159.2`, and permission-file SHA-256 checked locally | Pass |
| Independent workspaces and exact resumed snapshot | Turn 2 resumed turn 1's native thread after a host-runner process restart and read `FIRST-RUN`; turn 3 used a different thread and observed that the marker was absent | Pass for tested native runs |
| Pinned whole-skill bytes | Fixture imported into private store at `sha256:a12c212a57a9bc8fa3f0ecd834c09f9576a37ee89e21c62a096b1213fcc2bef8`; fake-run snapshot retains bytes after canonical-store tamper | Pass for materializer |
| Missing or corrupt skill and workspace snapshots fail before turn | Unit tests plus a real missing-snapshot request returned HTTP 400, `post_run_snapshot_mismatch`, with unchanged ledger; snapshot restored afterward | Pass for tested missing snapshot; corruption covered by unit tests |
| Failed, cancelled, or timed-out run retains run ID, category, and partial raw events | HTTP tests returned 502 with run ID and terminal category, with prior `item/started` retained; accepted cancellation returned 202 | Pass for runner logic |
| Turn cap survives restart and counts submitted turns | Real ledger retained turn 1 across restart, reached 4/4 including cancellation, and rejected a subsequent request with `model_turn_cap_reached` before native thread creation; ledger unchanged | Pass |
| Real loopback HTTP refuses a turn at cap zero | `POST /v1/runs` returned a stable run ID and `model_turn_cap_reached`; no native thread ID was issued and the private turn ledger remained absent | Pass |
| Saved Langflow flow is structurally valid | Pinned Langflow 1.12.3 `Graph.from_payload` parsed 3 vertices and 2 edges | Pass for import shape only |
| Langflow component handles success and failure distinctly | Pinned-image `smoke_component.py` returned structured success data and raised an error containing the run ID and category on HTTP 502 | Pass for component logic |
| Native rollout export cannot select auth file | Credential-free export test accepts one matching sessions JSONL and rejects an `auth.json` path before any copy | Pass for export guard, real rollout pending |
| Langflow run API invokes the runner and returns its structured result | Imported saved flow completed turn 1 and returned answer, Laomedo run ID, native thread ID, pinned revision, and trace reference in Chat Output | Pass; Chat Output renders the object as JSON text |
| Langflow browser UI displays the result | Browser interaction was not tested | Unverified |
| Native Codex tool call with matching result | Turn 1's skill-read and fixture/marker commands have matching `item/started` and `item/completed` IDs, exit 0, and command output; host marker independently equals `FIRST-RUN` | Pass |
| Native thread resume after runner/app-server restart | Turn 2 used `/resume` with the saved thread ID and snapshot hash after restarting the host runner; a new Docker app-server reopened the same thread and read the marker, with unchanged post-run hash | Pass through runner API; saved Langflow node currently starts fresh runs |
| Fresh native run stays independent | Turn 3 ran through the same saved Langflow flow with a new native thread; tool output and host inspection both show no prior marker | Pass |
| Interrupted Langflow run retains partial events and fails the flow | Historical turn 4 cancellation followed an observed `commandExecution` start; runner status became `cancelled`, 39 native events remained, and Langflow returned HTTP 500 containing the run ID and `failed: cancelled`. Container termination was not checked at cancellation time. The later runner revision sends `turn/interrupt` and forces named-container removal; a no-model Docker canary verified removal, but turn 4 was not replayed. | Status and partial events retained; historical turn termination unverified; process-crash interruption not tested |
| Private rollout imports through AGENTVIZ | Deferred at the user's request | Deferred |
| Skill was read or invoked | Turn 1 completed an explicit native read of `/draft/.agents/skills/laomedo-pilot/SKILL.md`, exit 0, with the fixture skill body in the result | Read observed; invocation/compliance not inferred; component still conservatively reports `offered` |
| Codex inner token usage | The component does not extract inner native usage counters | Unknown in the Langflow result, not zero |

The result is a **go for the tested single-user local Langflow-to-Codex path**.
The first run, native restart/resume, fresh-run independence, missing-snapshot
rejection, and cancellation status were observed. The historical cancelled
turn's container termination is unknown. AGENTVIZ remains deferred and the
browser UI was not exercised, so this does not satisfy every original check
in issue #11. Resume was tested through the runner API, not through a saved
Langflow resume node. The ledger is **4/4**; further model calls require new
bounded authorization. The existing Docker permissions are unchanged; this
matrix makes no hosted, multi-user, or broad network-isolation claim.
