# EXP-104 amendment 15: consumed identities, integrated redaction test, and S4 preflight

Date: 2026-10-07. Status: frozen after independent review of `0067a61`
and before the changes below or any S4 provider effect. The reviewer found
that a new state directory could reuse S3-01 despite its unknown write, and
that the diagnostic journal's secret test did not exercise the full path.
S3-01 remains `unknown`; its A effect is never resent.

The probe must refuse every known consumed identity before creating state or
contacting the provider: `exp104-d2-20261007-01`,
`exp104-d2-20261007-02`, and `exp104-s3-20261007-01`. A regression must
show each is refused even with a fresh state directory. The diagnostic test
must feed secret-bearing fake Git stdout/stderr through the real Git transport,
journal wrapper and durable mediation store, and then prove that neither
journal nor database contains the secret, the effect stays `unknown`, and a
repeat makes no second transport attempt.

The next distinct identity is `exp104-s4-20261007-01`, with branches
`exp104-s4-20261007-01-{a,b,c}` and connection ID
`exp104-s4-selected-gh`. The selected `GH_LAOMEDO` token and disposable
repository are unchanged; the tested code SHA must be supplied at launch.
Before any live write, perform a Git `push --dry-run` against **S4's new A
branch** through the same host-side credential helper, then independently
verify the branch is still absent. A nonzero dry-run stops before live write;
capture only its numeric exit and fixed diagnostic category, not raw Git
output or token material. The dry-run is a guard, not proof that the real
push will succeed or that a token's provider-enforced scope is exclusive.
The [Git push manual](https://git-scm.com/docs/git-push) says `--dry-run`
does everything except send updates; a local bare-repository control also
confirmed that it created no ref. Git `--porcelain` sends per-ref status to
stdout, so classification may inspect both streams but persist neither.

On any S4 failure, the sanitized observation must include the fixed diagnostic
record if one exists, the durable effect state, provider-attempt count and
exact-container cleanup. It must not upgrade `unknown` from a 404 ref lookup
or retry any uncertain write. S4 is one-shot; if it fails, record and stop
that identity. A separate subsequent identity requires a further frozen
amendment. Even a pass remains candidate evidence, not production account
connection, full `git`/`gh` parity or real-agent Q11 acceptance.
