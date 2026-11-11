# Real Codex split Agent restart reconciliation - 2026-11-11

Implementation0fdacaa78. One actual user-authorized Codex model invocation used the existing access-only session adapter in a uniquely owned disposable workspace/profile. A real shell command wrote acceptance-active.txt and slept. Both controller and credential-free executor were independently observed running, each with its exact durable receipt. Only the child Python owner was terminated; both native containers were then still running.

A new CodexAgent on the same state, with the same explicitly supplied split composition, ran its normal constructor recovery. Both exact resources disappeared and their receipts cleared, status became interrupted with runner_restarted, cancellation confirmation was not fabricated, and resume was refused with resume_binding_mismatch. A separately owned same-image sentinel stayed alive. Temporary profile/private state were removed after exact cleanup. No native conversation, access/refresh token, account identifier or private receipt is retained here.

```json
{"stage": "active_native_execution", "model_command_marker_observed": true, "owned_receipt_count": 2, "owned_running_count": 2, "split_mode_unsupervised": true}
{"stage": "agent_restart_reconciliation", "running_orphans_after_owner_exit": 2, "record_status": "interrupted", "error": "runner_restarted", "cancel_confirmation_unchanged": true, "exact_owned_absent_count": 2, "pending_receipts": 0, "foreign_sentinel_alive": true, "resume_refusal": "resume_binding_mismatch", "activity_closed": false, "activity_complete": null, "activity_reason": null}
{"stage": "temporary_profile_cleanup", "removed": true}
{"stage": "private_state_cleanup", "removed": true}
```

Activity remained closed=false, complete=null, reason=null: the dead owner never sealed its native/telemetry ends. This observation is not claimed as terminal Activity-stream recovery. No successful run or cancellation is inferred from container cleanup. This establishes one real split Codex constructor-restart case, not Claude/OpenCode restart, supervised lease loss, process-tree kill, physical host/daemon loss or automatic recovery without reconstruction. No daemon reset, prune or unrelated removal was used. New harness and conclusions are fully unreviewed - reviewer pending. No whole-PR approval.
