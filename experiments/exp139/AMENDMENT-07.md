# EXP-139 verifier composition correction, 2026-10-12

AMENDMENT-06 ran once at `190de01a6e2157ca521ba91a1aaea2b72fe2e742`,
manifest `6e7b5b4bbdc8debd2375685cd66a15f43db5fd5315d95a1d1e548a6961cc560c`.
The branch prerequisite was satisfied and the relay froze one private bundle.
The verification callback indexed `advertised_commit` in the freeze receipt,
but that receipt has no such field. The callback swallowed the exception before
the Docker verifier started. The helper timed out waiting for verification,
and the imported graph selected rejection. No provider push or PR was attempted.
The ledger is 6/10. Cleanup passed, all grants are revoked, and host trees stopped.

Correct the composition to use the existing `_read_frozen` routine. It verifies
private roots, run binding, regular files and the captured bundle checksum,
then extracts the sole allowed branch's advertised commit from the frozen
header. Use that commit for verification and downstream artifact resolution,
rather than assuming the raw receipt contains it. This parses captured bytes;
it never executes Git against agent-owned configuration on the host.

A regression uses a real producer receipt and captured bundle, invokes the
composition's verifier boundary with a mocked Docker verifier, and asserts the
commit reaches it. A tampered bundle refuses before the verifier is called.
The earlier dummy relay controls remain applicable; they did not test this
receipt-to-verifier integration and are not live acceptance.

Prepare one fresh success request and authority identity, retaining the explicit
branch prerequisite and all eight consumed requests. Archive AMENDMENT-06 inputs,
activation, logs and outcome. Preserve six used turns, maximum ten total, and
unused one-push/one-draft-PR attempt budgets. Never retry a consumed request or
an unknown provider effect. Failure/rejection cases are not resubmitted.

The concrete startup remains the same two independent hidden processes, port
8779, 600-second handoff, pinned images, subscription volume, fixed repository
and branch, scoped mediator/relay, network-off commands, exact auth denial and
approved `.git` write. The same-UID relay residual remains accepted local scope.
No new credential, permission or network route is requested. Activate the
corrected source and fresh inputs only after exact Claude review, passing
tests/CI and owner approval of this recovery; no live turn is authorized by
this document alone.
