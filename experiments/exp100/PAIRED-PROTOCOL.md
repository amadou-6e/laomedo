# S11: paired native command comparison, synthetic provider

Issue #100. Governing specs b319630ecf25f147bef9e19e2957f6ab8ab3ac59,
selected classifiers f6f279f1785aeba5a9ec9407d716e894fecc8fb1. Freeze before
new adapter/harness code and any evidence execution. No real GitHub credential,
live GitHub acceptance write, model turn or production permission widening.

## Paired boundaries

Use equivalent independent provider states and fresh direct/mediated identities.
Direct: actual installed Git/gh CLI, isolated Git configuration and empty gh
configuration, explicit synthetic credential only for loopback fake HTTP API.
Mediated: pinned Git-capable agent container, normal git/gh commands on scoped
PATH, production remote helper/client/store/transports and trusted local fake
provider injections. Never read host gh/GCM/token sources. Underlying provider
credential remains host-only; container gets only a run capability.

For HTTP baseline, `gh api http://127.0.0.1:PORT/...` supplies actual CLI request
semantics to a fake provider. Do not call this a same-syntax comparison of native
`gh pr`/`gh issue` high-level GraphQL internals: compare authorized effects and
normalized fields separately from raw output/syntax differences. Direct Git
uses separate local bare state; mediator's injected trusted Git transport maps
its exact selected HTTPS target to another local bare state. This is synthetic
endpoint/transport parity, not real GitHub/HTTPS/authentication acceptance.

## Scope and cases

Local Git: status/diff/add/commit. Remote Git: fetch scoped base/run branch,
first and second fast-forward pushes, explicit force/other-ref/multi-ref refusals.
PR: create/read/edit bound target, body file/stdin, classified API POST alias,
wrong repository/base/PR, changed readback and lost response controls.
Issue: read/list and exact reviewed IF-12 create; unreviewed/edited draft refused.
Actions: list/read fixed same-repo resources; wrong repository refused.
REST: fixed GET and selected PR POST; extra fields/methods, paging/default POST
differences, arbitrary unclassified writes visibly unsupported.
GraphQL read/mutation/variables/paging remain unsupported on mediated side;
record direct baseline and mediated refusal as unsupported, never equivalent.
Credential export/auth/aliases/extensions must refuse before any provider call.
Concurrency/loss: revoke A, show retained A denied/no dispatch and B continues;
same confirmed/unknown identity cannot repeat, altered content conflicts.

The harness's trusted controller may explicitly issue a MediationStore scope
for already implemented operations, including reviewed_issue_requests. Existing
RunGrantAuthority/LocalRunner first-slice operation sets remain unchanged; this
does not claim those defaults publish issues or list through new permissions.
Issue adapter forwards a proposal identity, but only host exact reviewed-request
hash permits the effect. Unreviewed drafts must never publish. New native issue
syntax must be reviewed with canonical specs before capture or merge.

## Evidence and gates

Freeze exact source/image/command vectors/input bytes and provider-attempt caps
in an independently reviewed pre-run manifest before the one-shot capture.
Fresh identity exp100-paired-s11-20261010-a, exclusive claim before execution;
failed/unknown capture consumes it, no replay or ambiguous write retry. Runtime
600seconds, per-command30seconds, cleanup30seconds; synthetic writes only.
Record actual exit codes, safe stdout/stderr categories, effect/run identity,
remote readback, provider counts, grant scope, credential/mount inventory and
cleanup. Label each case equivalent/different-but-authorized/unsupported/denied/
unknown with reason. No total parity claim from a subset; supported positives
must succeed and unsupported negatives must be visible with zero dispatch.

One shared checker must reject omitted/repeated/wrong-run/post-revocation effects,
missing positive cases, false equivalent labels or missing cleanup, with explicit
negative controls. Development tests are not campaign evidence. Preserve raw
sanitized observation LF bytes and committed hashes; record every deviation.
Independent pre-run/code and post-run/spec evidence reviews are required. No
issue closure until reviewer assesses #100's actual criteria and accepted merges.
