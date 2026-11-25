# Skill node controls

`skillChoicePlaceholder`, `skillFieldTemplate`, `isSkillControlHidden` and `skillNodeDescription` adapt node schema/state to Langflow controls. `skillFieldTemplate` displays a discovered folder path while retaining its exact underlying selection identity. The installer places this adapter beside upstream input rendering. It does not own registry discovery or editing.

`isSkillNode` identifies both Local Skill and GitHub Skill. `isGitHubSkillNode`
selects the connection controls only for the repository-backed node.
