# Skill viewer interface

`SkillViewerProvider` retains the requested workspace above transient canvas controls. `SkillViewerRequest` forwards an exact Skill/revision selection. `SkillInspectionError` projects safe inspection failures through the shared error catalogue.

Private selections additionally retain the explicit connection and repository.
They open the private read-only viewer even when a pin is missing or stale; they
never fall through to the public workspace. Changing connection invalidates the
source/Skill/revision resolution binding. Public requests retain their existing
three-part exact binding.
