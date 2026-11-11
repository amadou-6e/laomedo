# Single-action catalogue recovery acceptance

Implementation PR264 delta ce89c388 to95daff4a; specs a9eea673 to3b36bb1, later7856f9b corrects only diagram wording. Final matching frontend build succeeds1m14,37focusedtests pass, final-head CIgreen. No normal runner cap or servicepolicy change.

The actual owned runner was stopped, and auto-recovery.cjs used the real app to expose catalogue failure and click Start local runner once. Authenticated readiness triggered exactly one codex catalogue event and one automatic component update. Eight real models loaded, notice dismissed, graphbuilds0. No Agenttask/modelturn. Runtime evidence stays outsideGit.

To capture loading, browser forwarding of the unchanged read-only component-update request afterStart was delayed5000ms, then real serverresponse continued. This is controlled latency, notfixture or normal-latency measurement.

Recovered harness failures are not acceptance: first runneralreadyonline; next upstream assistant-onboarding tooltip's role dialog hid background error cards after10sec (preexisting PopupFrame behavior), even though automatic discovery fired. Final harness dismisses the actual tooltip beforeStart and captures visible states. No product fix for that independent tooltip interaction is implied.

Claude code/contract APPROVE at95daff4a/3b36bb1. Its lowA2 designwording correction is applied7856f9b. Existing catalogue listener emits settled in finally, supplyingA1 evidence. Actual screenshot/integration continuation APPROVE (same reviewer/session), A1 finally confirmed with a nonblocking question about an unmounted field; owner acceptance and governing spec/stack merge gates remain separate.
