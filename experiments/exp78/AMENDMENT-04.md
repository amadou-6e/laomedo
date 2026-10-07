# EXP-78 amendment 04: metadata-only personal-root comparison

Independent review found that the shared feasibility helper hashes personal
session and auth file contents. It published only booleans, but reading those
bytes is unnecessary for this zero-turn discovery check. Before the final
host rerun, replace that helper with a local metadata-only snapshot of path
names, sizes, modes and modification times. Do not read personal file bodies.
Retain the same personal-root comparison categories. A changing session-root
snapshot while this IDE conversation is active remains attribution-unknown,
not evidence that the probe wrote there.
