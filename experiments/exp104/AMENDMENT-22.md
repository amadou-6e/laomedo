# EXP-104 amendment 22: clarify S7 capability scan

Date: 2026-10-07. Status: frozen before any S7 live call. This corrects one
contradiction in [amendment 21](AMENDMENT-21.md) without changing the S7
identity, write budget or acceptance threshold.

The exact run capability is **expected** in its one designated read-only
`/run/laomedo/capability` mount and in the host's private lease state. Those
two locations are not leaks. The pre- and post-run scan must instead prove:

- the reusable GitHub provider token appears nowhere in agent mounts,
  container environment/inspection, trace, stderr, HTTP response or committed
  evidence;
- each run capability appears only in its own designated capability mount
  and private host lease state, not in any other mount, captured output,
  environment value, response or committed evidence;
- a grant ID, capability path or mediator instance is not misreported as the
  reusable provider token or as proof of its absence.

The scanner must report counts by location, redact exact secret bytes before
persisting evidence, and fail the confidentiality claim on any unexpected
hit. It cannot rule out encoded or partial disclosure by an agent. No S7
provider call has occurred, so this amendment does not alter evidence.
