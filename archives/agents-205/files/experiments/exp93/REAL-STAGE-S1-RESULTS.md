# S1 real-stage attempt: incomplete, 2026-10-11

Protocol0b4af95 and amendment62ffc04 preceded executed source
8345768ab0165e772e0eee62cea952e642056b1d and independent pre-run approval.
The fresh single-use identity exp93-real-stage-s1-20261011-a is consumed;
it must never be reexecuted. The original machine observation is
[real-stage-s1-observation.json](real-stage-s1-observation.json).
Its SHA-256 is73f7b83a358f038768c97fe73274dfdbedb75fe7fc403c4d5e351c74c3f63d40;
the committed copy matches the private original byte-for-byte.

The probe reserved shared entry13, changing authorized cap12 to16 under the
owner's four-turn extension. Actual local model ledger reports one attempted
turn. A completed before the required active shell-command boundary, so the
probe stopped as incomplete/ValueError during dispatch. Zero provider writes.
Cleanup flags for both exact containers, grants, workers, stages and tasks are
all true. This is NOT a real-agent crash, revocation-timing or Q11 pass.

Read-only post-run inspection of whitelisted native metadata found no
commandExecution item, only user/agent messages and terminal turn/completed.
The model explicitly declined the command, interpreting the instruction to
avoid other file writes as conflicting with creation of the intended marker.
That model explanation is not a proved tool limitation. No attempt to weaken
the agent sandbox, change credentials or retry the same identity was made.
Private raw events and model messages remain private; this prose is a
post-run diagnostic, not prospective expected evidence or an original capture.

Independent review and hashes will be recorded before integration. Remaining
budget: three additional turns (shared13/16). A justified next experiment needs
a new identity, a clearer expressly permitted marker task, frozen prospective
source/protocol and independent pre-run review; it is not a retry of S1.
