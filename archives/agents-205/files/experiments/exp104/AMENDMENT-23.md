# EXP-104 amendment 23: token scope confirmation for S7

Date: 2026-10-08. Status: recorded before any S7 live call. This supersedes
only the independent token-scope-evidence requirement in
[amendment 21](AMENDMENT-21.md). It does not change the S7 identity, repository,
write budget, reviewer gate, or requirement for explicit approval of the
bounded live run.

The user who configured `GH_LAOMEDO` has confirmed that the token uses
**Only select repositories**, with only
`ga84jog/laomedo-exp104-disposable-20261007` selected. The user has stated
that this confirmation is authoritative and that no further scope check is
needed. Record this confirmation as the scope basis; do not request a
screenshot, repository enumeration, or other independent proof. A positive
GitHub API access check remains a functional preflight, not a substitute for
or a challenge to the user's configuration decision.

Never print, hash, or commit token bytes, and do not use ambient `gh` or Git
Credential Manager credentials. All other pre-run gates in amendment 21,
including independent review of the committed executable probe and the user's
confirmation of the particular bounded live run, remain in force. No S7
provider write or model turn has occurred as part of this amendment.
