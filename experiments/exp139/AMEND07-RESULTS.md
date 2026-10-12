# EXP-139 confirmed push, downstream rejection, 2026-10-12

AMENDMENT-07 was explicitly approved, reviewed by Claude at
`e1eaaa4272bb22e3b95da771a815166c09befedc`, and activated after all four CI
checks passed. Its executed manifest was
`3a0675e1c84886fa7906ed39115f099f51bafdc8f274f38f937408556ac63dc0`.
The fresh imported success graph submitted one turn. The ledger is **7/10**.
See [AMEND07-OBSERVATION.json](AMEND07-OBSERVATION.json).

## Observed result

- The verifier ran, the mediated Git push was confirmed, and the agent's push
  command exited zero. Exactly one experimental push attempt is consumed.
- Run `f1db640f-9f02-4655-88b8-76b1bd467f24` completed with closed native
  execution evidence, twelve items, and task outcome success. The host accepted
  its output and retained the finite handoff in `validation_pending`.
- The imported graph selected rejection before the terminal runner record was
  saved. It made no draft-PR attempt. The original bounded graph summary did
  not retain validation or runner error codes, so the immediate cause is
  unproven. Timing is consistent with an interrupted status read, not proof.
- A credential-free re-evaluation of the retained final answer against both
  frozen forms accepts it. This does not retroactively change the graph result.
- Host-only GitHub GETs independently read commit
  `835cbfa3375b6b880fadf9b40b47e1c9541e7ec1` on `exp139-20261011-a` and report
  SHA-256 `3de179af048ab7823ab1a088459309e802b5a0253263718a8ce33f911eb3a49b`.
  A PR listing for that branch returned none. The first readback script call
  failed its list-response decoder; the corrected GET-only call passed. Neither
  readback made a write or submitted a model turn.
- The original 600-second handoff expired. No grant was renewed. All GitHub
  grants are revoked, executor cleanup is verified, the two owned host trees
  are stopped, and port 8779 is released. Private evidence remains retained.

## Follow-up code, not activated

The component now retries up to three consecutive transient transport failures
when reading the same bound run, within its existing overall wait deadline.
It never repeats POST dispatch, publication or Git. HTTP refusal, malformed
JSON and identity mismatch still refuse immediately. Exhaustion preserves
unknown and partial evidence. A focused test recovers after one failed GET
with one POST and two GETs; an exhausted-read test preserves uncertainty.

The graph evidence summary now exports a closed allowlist of validation and
runner codes, execution status, and no answer, error text, path or credential.
An imported credential-free graph tests interrupted-read recovery through the
publisher with synthetic replies. This is not a live PR acceptance result.

The post-run code is not the AMENDMENT-07 executed source. Any new deployment
needs its own reviewed source/manifest and configuration approval. The original
one-push budget is exhausted; three remaining turns do not authorize another
push or renewal of the expired handoff. No direct publisher bypass was used.
#139 remains blocked on actual validated graph-to-draft-PR publication.

Scope remains a bounded single-user local test. The same-UID/profile relay and
unverified process-attachment boundary are unchanged. No hosted or multi-user
claim is made. No raw transcript or credential is committed.
