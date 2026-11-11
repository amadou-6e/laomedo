# Current Activity native acceptance

Workspace head c7548d3085cff26e9aa009f13a75bd695982b7e1. Executable code is
unchanged from reviewed3778e2714ac65b06071224fa915da171df489225. Date2026-11-11.
Docker27.3.1, contextdesktop-linux was checked read-only before these runs.
Prior docker_control_failed was not reproduced; no daemon reset or production
code change was made to obtain this result.

Two isolated harness runs, four authorized Codex prompts total: fresh+successful
resume; then fresh+resumed-prompt cancellation. All capture uses real RunnerServer
HTTP /activity -> ActivityCapture -> ActivityStore -> common display projection.
Repeated first-page reads and paging atlimit1 verify stable replay. The resumed
native thread is preserved while attempt identities differ. Harness bounds are
experiment-only, never production service gates. Session access credential is
used only in memory. No credentials, session/account IDs, native receipts or
workspace content are retained here.

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
  "resumed_cancellation": [
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
      "projection_revision": 7
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
      "record_count": 1,
      "item_count": 1,
      "stable_replay": true,
      "projection_revision": 4
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

Fresh/resume complete with expected marker and nonempty common records/display.
Cancelled resumed prompt reports requested=true, confirmed=true, cancelled status,
worker_errors empty, complete Activity capture with nonempty common history.
The harness observes entry into the prompt call then waits3seconds before
requesting cancellation; it does not establish that the requested sleep tool ran.
No latency or every-intermediate-delta claim is made.

These observations supersede the earlier corrected-head native blocker for these
Codex paths only. The earlier failed fresh remains unexplained and preserved in
2026-11-11-activity-recheck.md. This is not Claude/OpenCode or host-loss acceptance,
not native accounting proof for every provider, and not daemon-wide cleanup proof.

Reviewer implementation/spec/doc approvals are recorded for3778e2714 (later
review-header edits only). This new experiment-harness cancellation option and
evidence have not been independently reviewed. Full692 Agent checks still have
the existing19-member runtime-interface guard failure and4skips; no other failures.
PR250 remains draft, not approved for merge.
