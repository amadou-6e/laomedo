# Codex retrospective evidence

Experimental implementation for [issue276](https://github.com/amadou-6e/laomedo/issues/276), on `exp` only. Private databases, manifests and reports belong to the workspace's ignored `session-retro.local/`, never this package. No Agent production code is changed.

## Structure and nomenclature

`SessionReader` locates and verifies finite native byte ranges; `CodexEventDecoder` interprets records without executing them; `SessionIndex` persists bounded search values and source locators in SQLite. `RetrospectiveReport` constructs candidate episodes and coverage, not an automatic causal verdict. `Redactor` masks recognized secret forms; it is best-effort and never a guarantee that arbitrary prose is safe to publish. `ProcessMemory` measures this single-process CLI. Grouped values live in `models.py`; injected environment settings live in `settings.py`. `cli.py` contains only standalone command functions. No abstract base is needed for one implemented host format.

| Object | Methods and guarantees |
| --- | --- |
| `SessionReader` | `snapshot`: verify native identity and capture finite length; `records`: stream complete lines, verify restart prefix; `verify`: rehash indexed prefix; `read`: verify and return an exact record. Active appends do not move a captured boundary. |
| `CodexEventDecoder` | `decode`: normalized metadata and bounded redacted search text, preserving physical native record identity. Unknown types remain explicit. |
| `SessionIndex` | `build`: transactional batches/resume/explicit extend; `coverage`: reconcile records and call IDs; `search`: bounded indexed matches; `read`: bounded source-derived content; `verify`: detect source changes. |
| `RetrospectiveReport` | `write`: private coverage, user-intent timeline and candidate review queues; never silently convert candidates to confirmed incidents. |

## Processing contract

`EpisodeBuilder.write` streams user-message windows and final-answer source locations. These windows are not automatically independent tasks: continuations and scope changes require original-context review. `Incident`, `EvidenceReference` and `PreventionProposal` retain reviewed findings, counterevidence and unapplied controls. A tool failure or regex match is not a causal verdict.

Each JSONL record retains line, offset, byte length and SHA256. Large lines are scanned without retaining their payload, marked oversized and excluded from semantic-completeness claims. Malformed JSON, incomplete final bytes, unknown events, missing call partners and truncated search text are reported. Restart verifies the committed prefix and parser/settings version; explicit `--extend` admits later bytes only after verifying the old prefix. A completed build re-verifies the prefix before becoming complete. Source replacement/truncation fails closed. Source reads use Windows shared read/write/delete access; no source writes or model calls.

All native records remain source-addressable. `event_msg` representations are not silently deduplicated against `response_item` messages. Compactions and referenced child sessions are retained as observations, not recursively opened or counted as fresh requests. Search is over bounded extracted text, not guaranteed full-payload search. Original payloads remain in the source. Read pages declare omitted characters.

## Usage

Use Python3.12 with `pydantic>=2.13,<3` and `pydantic-settings>=2.14,<3`. Set `PYTHONPATH` to this directory, then run `python -m session_retro --help`. `index` requires an explicit source, expected session ID and private database path. `coverage`, `search`, `read`, `verify` and `report` use that database. No network or external inference is implemented.

`RETRO_` settings control chunk/record/batch/search/read limits. `--stop-after` is an interruption test aid for this experimental reader, not a limit on Agent model runs. Output is local, redacted best-effort, and private. Never publish it automatically.

Run internal controls with `python -m unittest discover -s tests -v`. They are parser controls, not real-session acceptance. Measure a fresh real index process separately; report source/parser revisions, memory, timing and remaining gaps. Read all evidence around a candidate before claiming a mistake or cause. Existing instructions at the incident time, counterevidence and later correction matter.

## Research lineage

Methodological references, not copied implementation:

- Supermatt retro `58dabace448725e473477545bead7633bd496274`.
- EveryInc compound-engineering-plugin `d307bdb7ce158fc47184097ec258007a1a8e7bb3`.
- pskoett-ai-skills `878b0e48bca74849c6219815882e75e60cfa2b72`.

This reader replaces whole-file extraction rather than wrapping its lossy output. Promotion into a reusable skill, independent review, persistent instruction edits and publishing private evidence are separate decisions.

Report generation requires a new private directory and exclusively creates files.
Native-type histograms and final-answer references are bounded by page_records;
omitted counts stay visible. Regression controls verify non-destructive refusal.
