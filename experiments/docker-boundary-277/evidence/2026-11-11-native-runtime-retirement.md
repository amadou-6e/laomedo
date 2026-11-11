# Native runtime-role retirement acceptance

Exact executable headacc9c41ae onrefactor/205, PR250. Base98d130bb9.
The unconsumed BaseAgentRuntime and discarded launch/observation wrappers were
removed; providers construct native lifecycles and keep existing close/cancel
factory conventions. These results do not waive independent review.

Real Codex, same registered image, modelgpt-5.6-sol/low, two isolated harness
runs of2prompts each: fresh+resume, fresh+resumed-prompt cancellation. Existing
explicitly authorized access-only session credential is used in memory; no
credentials/nativeoutput/sessionIDs retained. Aggregate results:

```json
{
  "fresh_resume": [
    {
      "stage": "admission",
      "provider": "codex",
      "image_id": "sha256:e0eddf0e62cd7a46e6050d3ec44adf87150965139e44f6dced15b748845e21ba"
    },
    {
      "stage": "discovery",
      "provider": "codex",
      "model_count": 8
    },
    {
      "stage": "activity_fresh",
      "status": "completed",
      "error": null,
      "reason": null,
      "stream_state": "complete",
      "closed": true,
      "complete": true,
      "record_count": 5,
      "item_count": 4,
      "stable_replay": true,
      "projection_revision": 8
    },
    {
      "stage": "fresh",
      "status": "completed",
      "error": null,
      "answer_ok": true,
      "model": "gpt-5.6-sol"
    },
    {
      "stage": "activity_resume",
      "status": "completed",
      "error": null,
      "reason": null,
      "stream_state": "complete",
      "closed": true,
      "complete": true,
      "record_count": 3,
      "item_count": 2,
      "stable_replay": true,
      "projection_revision": 5
    },
    {
      "stage": "resume",
      "status": "completed",
      "error": null,
      "thread_preserved": true,
      "answer_ok": true
    }
  ],
  "resumed_cancel": [
    {
      "stage": "admission",
      "provider": "codex",
      "image_id": "sha256:e0eddf0e62cd7a46e6050d3ec44adf87150965139e44f6dced15b748845e21ba"
    },
    {
      "stage": "discovery",
      "provider": "codex",
      "model_count": 8
    },
    {
      "stage": "activity_fresh",
      "status": "completed",
      "error": null,
      "reason": null,
      "stream_state": "complete",
      "closed": true,
      "complete": true,
      "record_count": 5,
      "item_count": 4,
      "stable_replay": true,
      "projection_revision": 8
    },
    {
      "stage": "fresh",
      "status": "completed",
      "error": null,
      "answer_ok": true,
      "model": "gpt-5.6-sol"
    },
    {
      "stage": "activity_cancel",
      "status": "cancelled",
      "error": "cancelled_by_user",
      "reason": null,
      "stream_state": "complete",
      "closed": true,
      "complete": true,
      "record_count": 6,
      "item_count": 3,
      "stable_replay": true,
      "projection_revision": 8
    },
    {
      "stage": "resumed_turn_cancellation",
      "prompt_started": true,
      "status": "cancelled",
      "thread_preserved": true,
      "requested": true,
      "confirmed": true,
      "error": "cancelled_by_user",
      "worker_errors": []
    }
  ]
}
```

Both flows exercise HTTP /activity -> ActivityCapture -> ActivityStore -> shared
display and stable replay atlimit1. Cancellation confirmed after nativeclose;
requesttrue,confirmedtrue,cancelledstatus,worker_errorsempty. Entry into prompt
call plus3secondwait precedes cancellation; no claim every tool began or every
intermediate delta was retained. No model counters/gates added to services.

Supporting tests: full693 Agent tests OK4skips; native architecture/lifecycle23
pass; Black878enumerated/7archivedexclusions pass. Full suite includes provider
injection, nativecleanup uncertainty, context exception delivery, history and
interface negative controls. Production runtime guard has no waiver/baseline.

Claude live acceptance awaits owner permission to mirror access-only login into
a temporaryprofile; no existing authenticated profile found. OpenCode awaits a
private authenticated profile path; no default production composition is added.
No host-loss or daemon-wide cleanup claim. New runtime retirement implementation
is fully unreviewed - reviewer pending at evidence generation. Prior Activity
approval does not cover it. PR remains draft; no merge.
