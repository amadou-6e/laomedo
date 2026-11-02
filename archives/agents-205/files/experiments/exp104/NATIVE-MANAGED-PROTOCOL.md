# EXP-104: managed native delivery and runner-loss S12

Prospective protocol, 2026-10-10. Issue #104; native operation coverage under
#100; exact-container lifecycle under #93. Record this before implementing
the executable. This document alone authorizes no capture. The exact final
source and executable require independent positive pre-run review.

Governing specifications: `amadou-6e/specs@ea2558e910d640b802b7b197d2a90b8d14e3249c`,
agent-execution authentication, github-write-mediation, decision 0004's scoped
Git reads, and decision 0005's active-run delivery/Windows task choices.
Production candidate before this protocol: `bac7ac114093f4373fe44cb76e46670db1fab68e`.
S10 A/B and historical S11 remain separate consumed identities, not evidence
for this executable. Do not modify or reexecute any historical capture.

## Identity, scope and prerequisite gates

Single-use identity: `exp104-native-managed-s12-20261010-a`. Only provider:
`ga84jog/laomedo-exp104-disposable-20261007`, repository ID `1408647759`.
Baseline: `1f1a505f2fbd31993a7946924a9bec5a27bb15c1`, base branch `main`.
Fresh unique run branches, PR markers, invocation/run/lease/effect IDs,
connection generation, durable databases and private workspace derive from
this identity. Refuse if any identity, claim, branch or marker already exists.

Use only the explicitly selected `GH_LAOMEDO` file reference. User-confirmed
repository-only scope is authoritative; do not demand a second exclusivity
attestation. Verify target repository ID, expected user `ga84jog`, unchanged
base and push permission through bounded read-only preflight. No ambient gh,
GCM, Git credential helper or environment-token fallback. Never publish the
token or capability. Existing unrelated tasks/files/containers are untouched.

The selected production host-services and verifier must be started through
the existing limited interactive per-user Windows task installer, not
threads or runner children. Refuse existing task names rather than replace
them. Record exact expected task actions/configuration ownership and PID
sets before any kill. An isolated interpreter must import required packages
from the pinned checkout without borrowing a user's credential profile.
Both task processes/heartbeats must be fresh before lease registration.

Zero model turns. Containers are scripted clients using the pinned Git image,
not Codex model invocations. They use production wrappers/client and native
Git/partial gh syntax. Trusted run records are controller-produced fixture
records, explicitly not a model runner's lifecycle attestation. Real
RunGrantAuthority and LeaseClient registration/renewal/expiry are required;
no direct store.issue or synthetic connection/lease authorizer bypass.

## Fixed procedure and effect budget

1. Persist an exclusive claim, exact source/spec/image and approval/review
   records before setup. Read-only preflight refuses changed targets or
   existing markers/branches. All configuration paths remain private and
   outside the agent mount. No provider credential in task argv/status.
2. Start the two independently owned tasks. Use their production configuration
   and host-only provider custody. No injected fake provider in this live
   case. Verify source/module origins, immutable baseline and fresh service
   identity. A service exit or stale heartbeat fails before dispatch.
3. Two separate runner fixture processes register durable A/B scopes through
   the real authority/lease path. Each has an exact owned container and a
   different branch. Allow only git_push/git_fetch/pr_create/pr_read/pr_update,
   run/base reads and explicit target binding. No issue/API mutations or
   workflow-file changes. A/B capability files are disjoint and read-only in
   their own containers; token file remains host-only.
4. In A while alive: native fetch of the approved base; local commit of its
   deterministic fixture file; native push; gh PR create with exact durable
   marker; gh bound PR readback. Persist each intended write identity before
   contact. Verify exact remote branch/commit/base/marker from readback.
5. In B while alive: native fetch, local commit and push to its separate
   branch. Keep its lease heartbeat running throughout A's loss/control.
6. Kill only A's exact runner process tree after checking PID/name/record
   ownership. Record host monotonic kill-completion time. Keep both task PID
   sets and B runner alive. Observe A lease revocation/cleanup using bounded
   read-only polling, without issuing writes during the detection window.
7. Once A is revoked, issue exactly one fresh PR-update effect against A's
   previously bound PR, through the SAME retained A capability from the
   controller (A's container may already be gone). Expect grant_unavailable,
   no additional provider attempt and authoritative unchanged PR readback.
   This is a controller refusal control, not an alive-agent command.
8. B uses literal gh PR create/readback after A's denial. Verify B's grant and
   exact commit/branch/base/marker; provider-attempt journal must show exactly
   two Git pushes and two PR creations, with no denied-update dispatch.

At most FOUR remote mutations: A push/create, B push/create. No automatic
retry, correction write, issue creation, Actions workflow-file mutation,
delete or merge. Native Git retries/repeated mutation must not occur after
unknown results. Bound each CLI call/poll and the overall procedure in the
executable before review. Timeout never means effect stopped; record unknown
and stop further mutations, then exact local cleanup. Remote refs/PRs remain
for audit. Reads may reconcile under the valid host credential without new
effects; they never justify reposting.

## Machine evidence and falsifiers

Commit sanitized machine observations and provider-attempt journal bytes
unchanged after privacy scan, with raw Git-blob SHA-256 and exact source pins.
Include command outcomes, branch/commit/PR identity readbacks, real lease
grant identities (not bearers), monotonic kill/revocation/denial times,
service PID sets/heartbeats, per-operation provider counts, A/B grant states,
ownership-checked agent/stage/task cleanup and exact-secret scan counts.
Do not call a declared budget an independent network-exposure measurement.

Required controls must be falsifiable: accepted post-revocation write,
revocation later than60s, B denied, extra provider mutation, changed target,
secret in agent state/output, task death, reused identity, wrong source,
unverified cleanup or unknown effect prevents pass. Add synthetic mutation
tests that reject at least these altered outcomes. A model-free test may
exercise checker logic; it is not substitute live evidence. Failed or partial
attempt consumes its identity and is retained, never silently rerun.

Always revoke exact grants and remove only exact owned local containers,
verifier stages, tasks and processes. Check ownership again immediately
before destructive cleanup. Do not delete shared roots or remote audit refs.
Loss of task ownership is unverified cleanup and requires reporting, not
forced removal. Track interruption/timeout state durably before handoff.

## What a pass would and would not establish

A pass would connect the independently managed Windows service launch,
production scoped authority/lease, while-alive supported native delivery and
real-provider A-loss/B-continuity path at ONE pinned current source. It is
not complete Git/gh parity, a real model result, Langflow Stop/Q11, Linux
systemd, multi-user secret isolation, task-service double failure, logout or
power-loss recovery. Full draft #105/#97 promotion still requires assessment
against their actual scope and independent review; no gate closes merely
because this protocol or its tests exist.
