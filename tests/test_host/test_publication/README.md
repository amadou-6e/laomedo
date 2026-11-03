# Publication verification

These controls protect host-owned input freezing and verified output preparation.
They do not authorize publication, start a real provider, or establish acceptance
of Docker, GitHub or a real graph.

| Concern | Test owner | Protected behavior |
| --- | --- | --- |
| Trusted input binding | `test_ingestion.py`, `BundleIngestTests` | Fixed run files, exclusive attempts, bounded input and path/link refusal |
| Frozen bundle execution | `test_bundle/test_stage.py`, `BundleStageTests` | Exact bundle identity, binary export, reviewed image and cleanup uncertainty |
| Container ownership | `test_bundle/test_ownership.py`, `BundleStageOwnershipTests` | Exclusive reservation, exact identity and safe orphan reconciliation |
| Verification worker | `test_bundle/test_verifier.py`, `BundleVerifierTests` | Claim ordering, trusted active bindings, status freshness and no redispatch |
| Host publication handoff | `test_handoff/test_store.py`, `PublicationHandoffTests` | Output validation, host publishing phase, per-run rejection isolation and uncertain readback |
| Verified Git snapshot | `test_verified.py`, `VerifiedStageTests` | Immutable snapshots, integrity, grant binding and unknown remote outcomes |

Each TestCase owns fresh temporary state. `setUp` prepares that case; existing
`test_*` methods retain distinct success, refusal, race and recovery assertions.
Tests that need an intercepted Git command import `CallbackGitRunner` from
`support.git`; the expected outcome stays explicit in the test.

The bundle leaf groups three related owners without repeating `bundle` in every
filename. Ingestion and verified snapshots remain separate concerns beside it.
Its stage checks call the installed bundle boundary directly. Campaign-only
composition controls remain archived on `exp`; no historical loader is needed
for these production assertions. No test imports another TestCase to borrow setup.

```powershell
python -m unittest discover -s tests/test_host/test_publication -t tests -v
```
