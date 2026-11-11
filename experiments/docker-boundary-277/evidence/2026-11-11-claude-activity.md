# Isolated Claude native Activity acceptance ? 2026-11-11

Implementation runtime code: acc9c41ae94ebd623df341620c1c75a2854502b4. The working tree also contained the BaseAgent method-order-only move subsequently committed as 68415e3dd; AST identity was checked. Model sonnet, effort low; registered Claude image shown below. User approved existing access-only login mirror into a uniquely named temporary Docker volume. No refresh credentials or private state are retained here.

Fresh execution, resume and cancellation after an observed common tool-call all passed through actual native Docker execution, HTTP Activity capture, owner-scoped store and common display. Repeated reads and limit-one paging remained stable; cancellation was confirmed. This is observed tool-call evidence, not proof that a requested 45-second sleep completed.

```json
[
  {
    "stage": "admission",
    "provider": "claude",
    "image_id": "sha256:e62a25ea4b5672d6f2ce0ab3d8f48053ca1642e48585aa39e75ce9d4efdea95f"
  },
  {
    "stage": "readiness",
    "ready": true,
    "reason": null,
    "scope": "native_subscription_authentication"
  },
  {
    "stage": "discovery",
    "provider": "claude",
    "model_count": 5,
    "selected_model": "sonnet",
    "effort": "low"
  },
  {
    "stage": "fresh",
    "provider": "claude",
    "status": "completed",
    "error": null,
    "capture_reason": null,
    "closed": true,
    "complete": true,
    "stream_state": "complete",
    "record_count": 6,
    "item_count": 4,
    "stable_replay": true,
    "thread_preserved": true,
    "cancel_confirmed": false,
    "answer_ok": true
  },
  {
    "stage": "resume",
    "provider": "claude",
    "status": "completed",
    "error": null,
    "capture_reason": null,
    "closed": true,
    "complete": true,
    "stream_state": "complete",
    "record_count": 3,
    "item_count": 3,
    "stable_replay": true,
    "thread_preserved": true,
    "cancel_confirmed": false,
    "answer_ok": true
  },
  {
    "stage": "cancel",
    "provider": "claude",
    "status": "cancelled",
    "error": "claude_cancelled",
    "capture_reason": null,
    "closed": true,
    "complete": true,
    "stream_state": "complete",
    "record_count": 6,
    "item_count": 4,
    "stable_replay": true,
    "thread_preserved": true,
    "cancel_confirmed": true,
    "active_tool_observed": true,
    "requested": true
  },
  {
    "stage": "temporary_profile_cleanup",
    "removed": true
  }
]
```

The auth volume was removed successfully. The initial harness then exited with a Windows PermissionError while deleting its temporary supervisor log, because its outer finally had not yet closed that log. The harness teardown was corrected to stop its supervisor and close its log before TemporaryDirectory.cleanup; the exact remaining owned directory was removed after containment checks. No inference was repeated merely to verify that teardown edit. Consequently all model-flow assertions passed, but the original overall process exit was not successful. Current harness cleanup changes are not claimed as live-tested.

Runtime retirement code/specification is independently approved at 98d130bb9..acc9c41ae; Activity at ebf74f27..3778e2714. This new harness and acceptance interpretation are fully unreviewed ? reviewer pending. No whole-PR, host-loss or daemon-wide cleanup acceptance follows from these observations. No production authorization gates or turn caps were added.
