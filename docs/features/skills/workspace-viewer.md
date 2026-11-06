# Find and full-page viewing

Expand Find in the sidebar or press Ctrl/Cmd+F to search text files in the working
Skill. Results form a folder/file/line tree. Selecting a line opens current source
at its match and exits historical comparison. Binary files are not searched.
Aa enables case-sensitive literal matching. Results stop at 500 matching lines
and ask for a narrower query.

Click Find again to collapse it while retaining the query. Escape inside Find
collapses it and returns focus to its heading. Folder disclosure is independent
of file selection and survives query changes. Search includes unsaved text when
editing is authorized.

Full page and Restore window use icon buttons with accessible names. Both retain
the selected file, comparison, tabs, sidebar width and search state. Markdown uses
one Preview Markdown/Show source icon, not a separate Source/Preview bar.

Background canvas refresh retains an open workspace and its buffers. Changing the
selection aborts old reads so late results cannot replace a new selection.
Flow switching while history is offline inherits upstream placeholder-history
constraints; it does not establish fresh-history or session-restoration support.
