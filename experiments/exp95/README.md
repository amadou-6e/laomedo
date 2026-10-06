# EXP-95: same-user approval boundary

`python -m experiments.exp95.probe` is credential-free and uses no model,
network, real authenticator or personal profile.

**Phase 1 (negative control).** A separate same-user process calls the legacy
`LocalGrantAuthority.issue()` fixture and mints one grant without any human
approval. This remains true; that issuer is a fixture, not an approval boundary.

**Phase 2 (protected authority).** `laomedo.work_graph.approval` accepts a grant
only after a registered WebAuthn ES256 credential signs a challenge derived from
the exact request (request ID, nonce and canonical request digest), with user
presence and user verification. Every redemption re-verifies the stored
assertion against the trust anchor and the stored request. A separate same-user
attacker process with ledger write access but no authenticator key tries to
(a) forge a grant row, (b) edit an approved request and recompute its digest,
and (c) replay a real assertion onto its own request. All three are refused.
`ES256` verification is pure Python and checked against the RFC 6979 A.2.5
known-answer vector in `tests/test_approval_authority.py`.

**Not established (reported by the probe):**
- The trust anchor (registered public key) and the ledger are still writable by
  the same user. A same-user process could register its own key, or reset
  `redeemed_at` to re-redeem an already human-approved request until it
  expires (`test_residual_same_user_ledger_reset_replays_only_that_approval`).
  Closing that needs the OS boundary from specs #246: a dedicated service
  identity and ACLs on the trust anchor, ledger and issuer code. Creating that
  identity requires administrator rights and was not done.
- No real authenticator ceremony was run; the tests use a software fixture key.
- The operator must see the canonical request in a UI the protected authority
  controls, and the authority must refuse ceremonies it did not start.
  Platform prompts do not display the request.

`boundary_passed` therefore stays `false` until the service identity, ACL audit
and a real operator ceremony are tested.
