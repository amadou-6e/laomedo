# #95 protected Windows broker deployment gate

This is a proposed, unexecuted machine change. The current tests use a software
authenticator and run under the ordinary test identity. They do not establish
a same-user OS boundary.

The protected launch route needs a persistent broker process running under a
dedicated non-administrator Windows identity. Only that identity and machine
administrators may write its executable, configuration, registered credential
public key, request/grant ledger, frozen inputs and run store. The ordinary
desktop identity may submit a pending request and launch with a grant reference
through the narrow loopback API, but must not edit those files or invoke the
operator review method. The broker must select the fixed Work Graph launch
configuration; a client cannot supply a path, Docker option, or authorization
callback. The current `ApprovalService` and `LocalSavedFlowDispatch` implement
that API shape but are not installed as a protected process.

The broker must also be the only identity able to reach the **stage's Docker
Engine**. Protecting only the ledger is insufficient while the ordinary user
can call Docker directly. Two deployment candidates require review:

1. Grant Docker Desktop Engine access only to the broker identity. This may
   require removing the desktop user from `docker-users`, affecting ordinary
   Docker development commands.
2. Keep the desktop user's normal Docker Desktop access, but run protected
   stages on a separate daemon or VM whose socket is accessible only to the
   broker. This adds infrastructure and image-management work.

Before enabling either route, record the actual account SIDs, effective file
ACLs, Docker Engine access result for each identity, and the broker's process
owner. A same-user negative control must fail to edit or roll back the ledger,
replace the trust anchor or code, invoke an approval ceremony, or create a
stage container directly. The broker must still accept a reviewed request,
redeem its grant once, and dispatch the exact frozen stage. Kill the broker
before approval, after the authenticator returns, and after grant redemption;
on restart, lost responses must resolve to the same grant or an explicit
unknown, never a silently minted second grant.

An SCM Windows service cannot display an interactive approval UI from session
0. The selected route therefore needs either a persistent interactive broker
under the protected account or a service-controlled UI helper in the user's
session. A real WebAuthn ceremony must pin the RP ID, exact origin, credential
ID, algorithm and user-verification behavior and show the complete canonical
request before the service initiates the challenge. No fixture key, copied
assertion, typed confirmation, or same-user process flag substitutes for it.

No account, ACL, group membership, Docker setting, service, credential, or
browser profile has been changed by this branch. Installation and the first
real ceremony require a separate reviewed machine-change authorization.
