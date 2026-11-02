# EXP-78 result: Codex offered a private pinned skill

Issue: [#78](https://github.com/amadou-6e/laomedo/issues/78).
Protocol commit `8d22b4238f532b0806780a3bec53413cd3b4c73d` preceded the
first run. Classification amendment commit `c398dca` and native-event
amendment commit `7f5bab9` preceded the first retained host observation.
After review, metadata-only amendment `cf19be5` preceded the final
[sanitized host observation](observation.json), SHA-256
`da6f386af0913ac63598cb0982a0e7ddb6b3d6214f2a76e7f862cf56b9392ac2`.
No credential was copied into the probe profile or used for authentication,
and no model turn was submitted. Earlier host probes read personal auth and
session bytes only to hash them; the final host probe compares metadata and
does not read those file bodies.

The first run listed the fixture once but was inconclusive on isolation: a
broad real-home prefix also included the disposable private profile in the
user's temporary directory, and the personal session-root hash changed while
this IDE session was active. Amendment 01 preserved that finding and narrowed
the listing classification before a rerun.

The retained host run used installed `codex-cli 0.155.0-alpha.16.3`. The sole
synthetic project skill appeared exactly once in `skills/list`, at its
effective private project path, without an explicit skill input, path mention,
thread, or turn. Six other listed skills lived in the private `CODEX_HOME`;
none resolved under either personal skill root. Source, effective-before and
effective-after `SKILL.md` SHA-256 values all matched
`bf309edde83f7eb908695c0c370ef4f467b348627d0c8e3de4d137be7b4756bc`.
The personal skill, session and auth-root metadata comparisons were unchanged
in that final host run. The observation includes a sanitized projection of
the native `skills/list` response and its request shape. Raw app-server logs
and the disposable profile were deleted.

After Claude's bounded review, amendment 03 and the pinned-image probe were
committed before the Docker run. A version-recording correction at `f6241b9`
preceded the retained [Docker observation](observation-docker.json), SHA-256
`9e22f55b8d9c99c95f500b1c8bc7ee4be1d58509cfc150411bb01b964f4bd9bc`.
The exact image ID was
`sha256:7b79ce12be47d6c8262dd4043895112d204416bda5cd891d124775df55587239`
and reported `codex-cli 0.159.2`. With no network, credential mount or model
turn, its native `skills/list` response offered the same fixture exactly once
at the read-only private project path. Five other skills were under the
container's private `CODEX_HOME`; none was outside the private project/home
roots. Source, effective-before and effective-after bytes matched the host
fixture hash above. The exact disposable container was removed.

**Conclusion:** both the installed host build and the runner's pinned Docker
build **offered** the private pinned fixture. No native event proves that a
model read its body, so `used` remains unknown. This does not establish a
model-initiated skill read or behavior under a model turn. A separate
model-backed comparison would require a credential decision and its own turn
cap. The probes did not attempt that comparison.
