# Prospective S10 B: confirmed-stage progression

Before implementation and capture. S10 A is failed and consumed; preserve its
observation/results. It stopped on second freeze after a confirmed first push,
with one provider push and no REST call. Do not alter or replay its identity.

Fix the production freeze gate: a prior frozen stage may permit a NEW capture
only if the host resolves that exact immutable stage through the existing
run/grant/branch/baseline, verification, bundle-hash and cleanup checks AND its
stage digest has a confirmed git_push entry in the mediator journal for the
same run and grant. The agent cannot supply an override, predecessor status,
digest approval or host path. Default/raw freeze callers retain refusal unless
the trusted callback is configured. A still-unknown branch write blocks freeze
before reservation. No automatic recovery/retry of unknown captures or writes.

Development controls must reject unconfirmed, unknown, altered, differently
bound and unclean stages, while allowing a confirmed cleaned stage. Factory
wiring in host services and the scripted capture must use the same host-owned
callback; callback errors fail closed. Freeze lock and exclusive stage identity
remain. This changes next-capture eligibility, not provider permissions or CAS.

Fresh identity `exp100-native-s10-20261010-b`: repeat the already frozen S10
08/09 cases and limits with the corrected progression path, new workspace,
provider repository, run/grant/effect identities and claim. No real token,
GitHub provider or model turn. Same-run fast-forward only; existing-branch
cross-run adoption remains unsupported. Synthetic owner-checked renewal is
unchanged. Exact revised source and independent pre-run review are required
before claiming this identity. Run once; preserve any failure/unknown.
