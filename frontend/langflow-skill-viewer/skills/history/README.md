# Immutable revision history

`CommitTree` reads paged commits and selects one. `RevisionDiff` loads that immutable revision and compares the selected file to the current working file. `SkillFileDiff` renders the comparison without mutating either revision.
