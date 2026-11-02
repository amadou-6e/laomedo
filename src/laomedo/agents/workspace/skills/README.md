# Agent Skill delivery

This leaf installs and verifies immutable Skill files in one Agent working copy.
utils.py owns install, verify, remove_owned_tree and the focused exclusion/hash
helpers. WorkspaceSkillError in errors.py preserves the stable refusal categories.

install records the exact owned exclusion state and returns its restoration data.
verify checks supplied immutable references before use. remove_owned_tree admits
the owned path before removing it; cleanup must not touch source or registry bytes.
These functions belong to Agent execution rather than general Skill discovery or
editing. Public reference and error payloads remain defined by their owning modules.
