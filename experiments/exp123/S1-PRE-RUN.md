# EXP-123 S1 pre-run candidate

Candidate source: `f5b2e9a257fe59e3f281300358d209c41546b76a`.
Governing specs: `86d6fcff5c6d51e6ad106daf59f3f7036c7f9e8b`.
Frozen protocol amendment: `44a6d238bee6c59ed6a9f0e5c46b06d32271f390`.

Fresh identity family: `exp123-S1-{success,early,pending,repair,cap,stop,crash}`.
Disposable container and labelled volume: `laomedo-exp123-s1-20261009`.
Budget: zero model turns, zero GitHub provider writes. One dispatch per case;
no retry after failure. The controller captures raw journal, each case snapshot
and each frozen graph, hashes their bytes, checks their consistency, and verifies
cleanup. A missing capture or unverified cleanup invalidates a passing summary.

Before pre-run review, two pure local control tests passed. A build-only check
on the pinned image constructed seven vertices without calling `Graph.arun`.
Neither is evidence for a graph execution. No case has been dispatched.

Execution requires an explicit independent approve verdict on the candidate.
Use `python -m experiments.exp123.probe --record S1 --source-commit
f5b2e9a257fe59e3f281300358d209c41546b76a` after approval. Preserve any failed
or uncertain result; a follow-up needs a fresh frozen identity and review.
