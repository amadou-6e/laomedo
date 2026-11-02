# EXP-104/S13: verified bytes as the sole local Git object source

Issue: https://github.com/amadou-6e/laomedo/issues/104. S12 is the
credential-free grant-bound resolver on draft #105. This protocol precedes
S13 implementation. The governing design candidate remains
`amadou-6e/specs@b5b27170523334cc886cb0ea27ec616bef44fd4e`.

## Question and boundary

Can the host import the immutable S12 snapshot into a fresh isolated Git
repository, classify the outgoing diff there, and retain that **same** object
repository for a later push? An agent checkout must not supply or override
objects. The S13 test remains local: no provider credential, remote GitHub
write, Docker, model turn, or `.env` access.

## Fixed cases

1. A verified snapshot imports its exact `refs/heads/validated` commit and
   pinned baseline into a new bare repository. The workflow-file classifier
   reads that repository and reports `False` for an ordinary file change.
2. A workflow-file change classifies `True`; a missing baseline, wrong commit,
   tampered bundle, invalid object graph, or unrecognized ref refuses before
   any credential supplier or transport call.
3. Mutate the agent checkout and original verified file after resolution.
   The staged object set and classification remain those of the S12 snapshot.
4. The staging API must make it possible to classify and push from the **same
   bare repository** in a later mediator integration; it must not silently
   fall back to a configured checkout.

Unit tests can establish this local behavior, but they are not a recorded
campaign run. A provider push or new live #104 attempt requires its own
frozen protocol, identity, pre-run review and authorization. Ambiguous writes
are never retried under a reused identity.
