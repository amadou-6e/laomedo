# Host publication

Publication owns admission, verification, staging and delivery of run-bound Git
output. It does not run an Agent or edit the Skill registry. Keeping these
responsibilities together makes the host trust boundary visible to callers.

| Concern | Package or module | Vocabulary |
| --- | --- | --- |
| Untrusted bytes admitted from a known run | `ingestion/` | `freeze_run_bundle`, `read_run_binding`, `validate_ingestion_roots` |
| Git-object verification | `verifier.py` | `BundleVerifier`: verify, reconcile |
| Bounded disposable staging | `bundle/` | `BundleStage`; owned stage admission and cleanup |
| Verified delivery | `verified/` | verify, publish and status functions preserve existing protocol |
| Authorized publication handoffs | `handoff/` | `PublicationHandoff`; persist and select explicit handoffs |

Names describe the responsibility. Base is reserved for an actual abstract
contract; a function is not wrapped in a controller simply to obtain an object.
Existing feature models remain canonical. Helpers shared by publication callers
are direct defining-symbol imports, not a cross-domain private utility alias.

This C2 checkpoint relocates ingress from `skills/ingestion/` without changing
Git policy, durable record formats, CLI names, authorization or error semantics.
It does not implement the later GitHub/Skill interface relocation or source Git
launcher redesign. A frozen bundle is unverified data, not permission to push.
