# EXP-78 amendment 01: distinguish installed skills from personal skills

The first credential-free run of the frozen protocol discovered the private
fixture, but counted seven skill paths under the real Windows home and saw a
change in the personal Codex session-root hash. That broad path test cannot
tell packaged skills under the VS Code extension apart from personal skill
directories. The current IDE conversation can also change its own session
file during the probe. The first run remains a failed and inconclusive
isolation observation.

Before rerunning, classify listed paths separately as private project,
private profile, personal `.agents/skills`, personal `.codex/skills`, Codex
installation, and other. Never print listed skill names or raw personal
paths. Keep the before/after personal-root hashes, but do not treat a changing
session-root hash as proof the probe wrote there while the IDE is active.
Report that comparison as confounded. For this zero-turn native discovery
case, pass only if the exact fixture is listed once at its effective private
path, effective bytes remain unchanged, no listed path is in either personal
skill root, and the personal skill and auth roots are unchanged. A model-read
claim is still prohibited.
