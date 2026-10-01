# Pilot evidence, issues #8 to #11

This matrix distinguishes current observations from acceptance checks that
require an end-to-end Langflow run. A missing observation is not a pass.

| Claim | Evidence | Result |
| --- | --- | --- |
| Existing Docker route can initialize Codex without a model turn | `--preflight` against pinned image and existing private volume returned model/effort list, `submitted_turns: 0` | Pass |
| Existing grant allows draft write and denies protected paths | Real app-server `command/exec` canaries returned workspace write exit 0, canonical and sibling store write exit 2, auth read exit 1; both sentinels unchanged | Pass for tested paths |
| Docker image, CLI, and permission file pinned | Image ID, `codex-cli 0.159.2`, and permission-file SHA-256 checked locally | Pass |
| Independent workspaces and exact resumed snapshot | Credential-free fake app-server tests; second fresh run starts without first run's `agent.txt`; restart resumes original thread from saved hash | Pass for runner logic, native acceptance pending |
| Pinned whole-skill bytes | Fixture imported into private store at `sha256:a12c212a57a9bc8fa3f0ecd834c09f9576a37ee89e21c62a096b1213fcc2bef8`; fake-run snapshot retains bytes after canonical-store tamper | Pass for materializer |
| Missing or corrupt skill and workspace snapshots fail before turn | Credential-free unit tests | Pass for runner logic |
| Failed, cancelled, or timed-out run retains run ID, category, and partial raw events | HTTP tests returned 502 with run ID and terminal category, with prior `item/started` retained; accepted cancellation returned 202 | Pass for runner logic |
| Turn cap survives restart and counts submitted turns | Persistent `turn-ledger.json` test; default cap zero | Pass for runner logic |
| Real loopback HTTP refuses a turn at cap zero | `POST /v1/runs` returned a stable run ID and `model_turn_cap_reached`; no native thread ID was issued and the private turn ledger remained absent | Pass |
| Saved Langflow flow is structurally valid | Pinned Langflow 1.12.3 `Graph.from_payload` parsed 3 vertices and 2 edges | Pass for import shape only |
| Langflow component handles success and failure distinctly | Pinned-image `smoke_component.py` returned structured success data and raised an error containing the run ID and category on HTTP 502 | Pass for component logic |
| Native rollout export cannot select auth file | Credential-free export test accepts one matching sessions JSONL and rejects an `auth.json` path before any copy | Pass for export guard, real rollout pending |
| Langflow UI and run API invoke the runner and display structured result | Requires test Langflow startup and bounded model authorization | Pending |
| Native Codex tool call with matching result | Requires bounded model turn and raw event inspection | Pending |
| Native thread resume after runner/app-server restart | Requires bounded model turn | Pending |
| Fresh native run stays independent | Requires bounded model turn | Pending |
| Private rollout imports through AGENTVIZ | Requires private run rollout; no raw transcript will enter Git | Pending |
| Skill was read or invoked | No native read event yet; answer content alone cannot prove this | Unknown |
| Codex inner token usage | No usage counter has been collected for this pilot | Unknown, not zero |

The current result is a **go for continuing a bounded local pilot**, not a
completed end-to-end acceptance. Until the pending rows are observed, issue
#11's end-to-end claim remains unverified. The existing Docker permissions are
unchanged; this matrix makes no hosted, multi-user, or broad network-isolation
claim.
