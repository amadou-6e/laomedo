# Startup correction, no additional permission or turn

2026-10-11. AMENDMENT-03 activation was approved by the owner and Claude at
0854420. Its fresh success request failed before thread/turn creation:
the app-server exited while loading permission configuration. Ledger remains
1/4, both write budgets remain unused; preserve this third run and its revoked
grant alongside the original failures.

A credential-free startup matrix found that the CLI's partial dotted override
requires an explicit default profile and misparses the literal `/draft/.git`
key. Use a complete inline TOML permission table instead. Restate the original
default profile and `approval_policy=never`, filesystem root read, workspace
write, exact auth-file deny, network disabled, plus only `/draft/.git=write`.
The effective policy is the owner-approved policy, not a broader permission.
Test exact invocation startup and direct sandbox denial before review/activation.

Keep all consumed digests and grants; never reuse the refused success request
or its grant. Archive AMENDMENT-03 exports/config/manifest/activation/results
outside Git. Prefix only the next success task with this startup amendment;
use a fresh host invocation ID. The still-unsubmitted failure/rejection requests
remain unchanged. The original remaining three turns and one-attempt budgets,
600-second deadline, supervisor selection and publication checks are unchanged.
Refreeze actual source/input bytes and obtain one focused blocking-fix review
before reactivation. No model turn is authorized by this document itself.
