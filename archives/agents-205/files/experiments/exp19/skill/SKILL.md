---
name: exp19-issue-report
description: Write a bounded, inspectable report from a frozen selected issue for the local Laomedo issue-to-agent-to-PR experiment.
---

# EXP-19 issue report

Read this skill file with a shell tool when asked to perform the EXP-19 local
test. Use only the selected issue text and frozen identifiers supplied in the
task. Write one UTF-8 Markdown file at the exact output path named in the task.
Include the selected issue URL, source body digest and graph snapshot ID, then
state one testable requirement from the issue and one remaining limitation.
Keep the report under 8 KiB. Do not run network commands, inspect credentials,
modify other files, or attempt to push a branch or create a pull request.
