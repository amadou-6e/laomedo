# EXP-78 result: Codex offered a private pinned skill

Issue: [#78](https://github.com/amadou-6e/laomedo/issues/78).
Protocol commit `8d22b4238f532b0806780a3bec53413cd3b4c73d` preceded the
first run. Classification amendment commit `c398dca` and native-event
amendment commit `7f5bab9` preceded the retained
[sanitized observation](observation.json), SHA-256
`c063605801bbcb95777f1002b92c70e4ba8534a07fddafd6940f0e20dd037198`.
No credential was copied or loaded and no model turn was submitted.

The first run listed the fixture once but was inconclusive on isolation: a
broad real-home prefix also included the disposable private profile in the
user's temporary directory, and the personal session-root hash changed while
this IDE session was active. Amendment 01 preserved that finding and narrowed
the listing classification before a rerun.

The retained run used installed `codex-cli 0.155.0-alpha.16.3`. The sole
synthetic project skill appeared exactly once in `skills/list`, at its
effective private project path, without an explicit skill input, path mention,
thread, or turn. Six other listed skills lived in the private `CODEX_HOME`;
none resolved under either personal skill root. Source, effective-before and
effective-after `SKILL.md` SHA-256 values all matched
`bf309edde83f7eb908695c0c370ef4f467b348627d0c8e3de4d137be7b4756bc`.
The personal skill, session and auth-root comparisons were unchanged in that
retained run. The observation includes a sanitized projection of the native
`skills/list` response and its request shape. Raw app-server logs and the
disposable profile were deleted.

**Conclusion:** the private pinned fixture was **offered** by this installed
Codex build. No native event proves that a model read its body, so `used`
remains unknown. This does not establish discovery in the pinned Docker
runner's Codex 0.159.2 build, a model-initiated skill read, or behavior under
a model turn. A separate model-backed comparison would require a credential
decision and its own turn cap. The probe did not attempt that comparison.
