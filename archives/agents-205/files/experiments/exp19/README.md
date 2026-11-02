# EXP-19 local integration probe

The completed [phase-zero probe](probe.py) uses a fake agent and local Git only.
Its [observation](observation.json) establishes that the existing Work Graph,
run store and raw-event store can retain a coherent synthetic binding.

The [live probe](live_e2e.py) selects Laomedo issue #49 through
the read-only issue connector and a source-complete Work Graph snapshot. It
freezes the current issue, imported Langflow flow, pinned skill, model/effort,
runner image and permission config before dispatch. The local Codex runner uses
the existing private subscription login volume. The agent command container
never receives a GitHub credential. Only the trusted host publisher may push
the one selected output artifact and open a draft PR after a separate grant.

The phases are deliberately separate:

1. `prepare` freezes issue and flow inputs in private state without a model turn.
2. `flow-preflight` imports and round-trips the saved flow on an approved local
   Langflow server without a model turn.
3. `run` requires an explicit private `grant.json`, submits at most one turn,
   and retains the native trace and verified output artifact outside Git.
4. `publish` requires the exact repository, branch, base and one-draft-PR grant.
   It verifies the selected artifact again, creates `test/49` from `develop`,
   and binds the confirmed PR URL and commit to the selected issue and run.

The approved local server configuration in [compose.yaml](compose.yaml) uses a
separate Langflow data volume and localhost port 7863. Its auto-login is
appropriate only for this disposable, localhost-only experiment. The runner
uses port 8769 and a separate private state directory. The user granted six
submitted turns and one draft PR from `test/49` to `develop`. The first 6/6
attempt completed a native agent turn but produced no selected output file.
Its [negative result](https://github.com/amadou-6e/specs/blob/docs/49/projects/laomedo/experiments/issue-agent-pr-integration/iterations/2026-10-05-local-e2e/results.md)
remains part of the record. [#68](https://github.com/amadou-6e/laomedo/issues/68)
records the subscription-login diagnostic.

The user then granted four more submitted turns. A direct agent-originated
nested-write diagnostic passed at turn 7/10. With the output parent present in
the source fixture and verified before dispatch, turn 8/10 ran through the
imported Langflow flow and produced the selected report. The trusted host
verified its bytes and published only that file in
[draft PR #71](https://github.com/amadou-6e/laomedo/pull/71), from `test/49`
into `develop`. The [retry result](https://github.com/amadou-6e/specs/blob/docs/49/projects/laomedo/experiments/issue-agent-pr-integration/iterations/2026-10-05-artifact-retry/results.md)
records the exact run, artifact and binding identifiers. The ledger is 8/10;
the one-draft-PR grant is consumed. This supports a bounded single-user local
path. Read-only inspection of the first attempt's private native trace found
that its report-write command exited with a missing-directory error: the
original fixture lacked the output parent. Whether the revised task wording
was also necessary remains unproved. No credential or private raw rollout
belongs in this repository.

The [spec protocol](https://github.com/amadou-6e/specs/tree/docs/49/projects/laomedo/experiments/issue-agent-pr-integration)
distinguishes this single-user local path from the deferred push-capable stage
and production browser-auth lifecycle.
