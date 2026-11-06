# Skill workspace navigation

The sidebar contains Find, Files and Commits. Each section collapses independently.
The SKILL menu offers Open all or Collapse all according to the current state;
Files and Commits have no redundant settings menus.

Files retain folder disclosure and open editor tabs. Drag the separator between
the sidebar and editor to change their widths. Selecting a commit beneath the
file tree shows the selected file's cumulative diff to the current working buffer, including unsaved text.
Selecting another file keeps that comparison. Added/deleted lines use the normal
visual diff, without raw diff commands or a combined all-file patch.

Current source returns to the current file. The history list includes the initial
import before edits; unchanged contents are identified without inventing a diff.
Unconfirmed file/history reads retain a descriptive error and their read-only
Reload files or Reload history recovery. Permanent unavailable, unsafe or oversized
revision refusals do not offer futile reloads. Reads never execute an Agent.
