# EXP-104/S14: bind a mediated push intent to one verified snapshot

Issue: https://github.com/amadou-6e/laomedo/issues/104. S12 resolves a
grant-bound immutable bundle; S13 imports it into a credential-free Git object
store. This protocol precedes S14 integration code. Governing design candidate:
`amadou-6e/specs@b5b27170523334cc886cb0ea27ec616bef44fd4e`.

## Question and boundary

Can the mediator obtain the S12 snapshot using the validated grant's run ID,
bind its digest to the durable push effect, and pass **that same snapshot** to
one S13 staging context whose classification and later push share a bare Git
repository? The agent can name `stage_attempt_id`, branch and commit, but no
host path, run ID, credential or repository override. The production path must
not fall back to checkout objects if the stage is missing or invalid.

S14 exercises synthetic/local transports only. Do not contact GitHub, read
`.env`, use a model, or spend a live #104 identity. Existing uncertain-effect
rules remain: an ambiguous prior push to the branch blocks an automatic new
effect; a repeated effect never resends.

## Fixed checks

1. A valid grant and stage identity produce a journaled intent whose request
   digest includes the stage digest; the transport receives exactly the
   resolved snapshot. Grant/record scope mismatch refuses before intent,
   credential, or transport.
2. Classify workflow files in the S13 staging repo, then use that same repo
   for a synthetic push command. A workflow change refuses before credential.
3. Replace the verified file after preflight: the dispatched snapshot and its
   digest remain unchanged. Repeating the effect is not a second dispatch;
   changing the stage under the same effect conflicts.
4. A lost/unknown push result stays unknown and blocks a new branch effect;
   no automatic retry. No checkout-object fallback is allowed in configured
   production service entry points.

The checks are local software tests, not evidence that a real GitHub grant is
revoked or that literal `gh` parity works. Any new provider write requires a
separate frozen, independently reviewed live protocol and fresh identity.
