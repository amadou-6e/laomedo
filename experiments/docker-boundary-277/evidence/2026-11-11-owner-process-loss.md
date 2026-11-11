# Shared Docker owner-process-loss controls - 2026-11-11

Implementation:0fdacaa78; generic recovery mechanisms unchanged from9bcb0149c.

Zero model prompts. These are real registered-image jobs/sessions, not actual provider Agent invocations. Both child owner processes were terminated while their exact containers were observed running. Recovery refused an active owner, a changed ownership-label receipt and a mismatched endpoint receipt; conflicts remained untouched and receipts retained. Matching exact recovery removed only the orphan and its receipt, and cleared a retained receipt after confirmed absence. A separately owned same-image sentinel stayed running throughout, then was explicitly closed. No daemon reset, global scan/prune or unrelated resource removal. Endpoint hashes and immutable IDs below record exact observations without publishing private receipt labels. This does not establish actual agent-level restart reconciliation, second-daemon execution, uncertain-create recovery or supervisor host-loss behavior.

```json
{"stage": "admission", "image_id": "sha256:e62a25ea4b5672d6f2ce0ab3d8f48053ca1642e48585aa39e75ce9d4efdea95f", "model_prompts": 0}
{"stage": "session_owner_loss", "endpoint_sha256": "30341252ca9aa2b298da11cd8527fdfbf8ab30a2f3b5a3c871188c778b20af30", "exact_owned_id": "229e59a4861e8e7c248f84dd1dc85cda44e63dbf6ec1d78c95cbc7693eff124b", "sentinel_id": "a697a79a8a59a97811ded59654e21521a022c1567f291ff9d518f637c69547a5", "wrong_labels_refused_and_retained": true, "conflicting_container_untouched": true, "already_absent_receipt_cleared": true, "active_owner_refused": true, "owner_terminated": true, "orphan_observed_running": true, "wrong_endpoint_refused_and_retained": true, "exact_container_absent": true, "receipt_removed": true, "repeat_recovery_ok": true, "foreign_sentinel_still_running": true}
{"stage": "job_owner_loss", "endpoint_sha256": "30341252ca9aa2b298da11cd8527fdfbf8ab30a2f3b5a3c871188c778b20af30", "exact_owned_id": "de29a0b526a8b4fa3e9d236ee0c2df09342a728bddd2cd195ee0a60f9f59bb9b", "sentinel_id": "a697a79a8a59a97811ded59654e21521a022c1567f291ff9d518f637c69547a5", "wrong_labels_refused_and_retained": true, "conflicting_container_untouched": true, "already_absent_receipt_cleared": true, "active_owner_refused": true, "owner_terminated": true, "orphan_observed_running": true, "wrong_endpoint_refused_and_retained": true, "exact_container_absent": true, "receipt_removed": true, "repeat_recovery_ok": true, "foreign_sentinel_still_running": true}
{"stage": "sentinel_cleanup", "confirmed": true}
{"stage": "private_state_cleanup", "removed": true}
```

New harnesses and these conclusions are fully unreviewed - reviewer pending. No whole-PR approval.
