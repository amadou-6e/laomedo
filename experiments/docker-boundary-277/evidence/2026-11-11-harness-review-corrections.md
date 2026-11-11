# Reviewer harness corrections - 2026-11-11

Production code0fdacaa78 unchanged and independently approved for rollout export (base9bcb0149c). The preceding exp artifacts throughf4166e17 received harness APPROVE and disclosed conclusions supported with HF01 caveat; earlier source/acceptance counts are not new runs here.

HF01: the earlier mismatched-endpoint control proved refusal/receipt retention but did not independently inspect the container immediately afterward. Its "untouched" claim was therefore not fully established by that run. The harness now requires the exact owned immutable ID still be running before matching recovery. The new real registered-image session and job run below passes that stronger control with no model prompts:

```json
{"stage": "admission", "image_id": "sha256:e62a25ea4b5672d6f2ce0ab3d8f48053ca1642e48585aa39e75ce9d4efdea95f", "model_prompts": 0}
{"stage": "session_owner_loss", "endpoint_sha256": "30341252ca9aa2b298da11cd8527fdfbf8ab30a2f3b5a3c871188c778b20af30", "exact_owned_id": "9888e5b607ecc561f8347dc5e9f9d942f3ab17fc84869ecdfeb776e36ba31791", "sentinel_id": "23fb55676b6f7ce7d572bbab32798c30dda7b798635289de075dc5795e6200c7", "wrong_labels_refused_and_retained": true, "conflicting_container_untouched": true, "already_absent_receipt_cleared": true, "active_owner_refused": true, "owner_terminated": true, "orphan_observed_running": true, "wrong_endpoint_refused_and_retained": true, "wrong_endpoint_container_untouched": true, "exact_container_absent": true, "receipt_removed": true, "repeat_recovery_ok": true, "foreign_sentinel_still_running": true}
{"stage": "job_owner_loss", "endpoint_sha256": "30341252ca9aa2b298da11cd8527fdfbf8ab30a2f3b5a3c871188c778b20af30", "exact_owned_id": "70b1ef4f87a0c128af3089cbdc58fcf948a14bc5f166c00c0eeacadeee9b5ee3", "sentinel_id": "23fb55676b6f7ce7d572bbab32798c30dda7b798635289de075dc5795e6200c7", "wrong_labels_refused_and_retained": true, "conflicting_container_untouched": true, "already_absent_receipt_cleared": true, "active_owner_refused": true, "owner_terminated": true, "orphan_observed_running": true, "wrong_endpoint_refused_and_retained": true, "wrong_endpoint_container_untouched": true, "exact_container_absent": true, "receipt_removed": true, "repeat_recovery_ok": true, "foreign_sentinel_still_running": true}
{"stage": "sentinel_cleanup", "confirmed": true}
{"stage": "private_state_cleanup", "removed": true}
```

HF03/HF04: Agent restart harness now removes its own temporary OpenCode profile even on failure, and derives the Codex profile from its generated temporary state even if failure happens before the parent constructs an Agent. Cleanup is in a finally nested after exact receipt cleanup/sentinel close, so it is attempted even if that cleanup raises. Its root must be the generated direct child of TEMP; an OpenCode profile resolving outside that root is refused. No shared/default profile is selected. Failure logs and receipts may remain; private access-only auth is no longer intentionally retained with them.

Zero-model helper verification created only an empty derived Docker profile, a synthetic noncredential OpenCode auth.json and another owned foreign sentinel volume. It verified both profile removals, sentinel survival and refusal of an unexpected root. These are real Docker/filesystem cleanup checks with synthetic data, not live failure/restart inference acceptance:

```json
{"model_prompts": 0, "codex_early_failure_profile_removed": true, "opencode_early_failure_profile_removed": true, "foreign_volume_untouched": true, "unexpected_root_refused": true}
```

No native model turn was spent merely to check teardown. The previously observed successful Codex/OpenCode restart and native export flows retain their original harness/revision bindings; later cleanup edits were not rerun as native flows. HF02 resume refusal remains only proof no fresh invocation was silently started, not independent proof of reconciliation. HF05 later Codex harness branch not rerun; HF06 repeating recovery must succeed before the hard-coded success field is reached. These limits remain explicit.

Corrections HF01/HF03/HF04 are implementer-verified; focused reviewer recheck pending. No whole-PR approval or merge.
