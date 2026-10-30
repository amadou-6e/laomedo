# Skill source discovery

`SkillSources` in `service.py` owns admitted source discovery, cached choices and
immutable resolution: `discover(source)`, `revisions(source, choice)` and
`resolve(source, choice, revision)`. It imports exact content without advancing
an existing canonical latest pointer, and never executes Skill code.

Fixed discovery exclusions and limits remain in this feature's `settings.py`.
External service Settings, the stateless client, module-level handler, listener
and trusted startup CLI live in `skills/interface/sources/`; its README defines
the transport object/method vocabulary and error projection. This keeps endpoint
configuration out of source policy without duplicating either owner.

Source/Git collaborator extraction and bounded shared Git execution are later
checkpoints; C3 does not claim to replace the existing launcher or establish real
source/edit/history graph acceptance.
