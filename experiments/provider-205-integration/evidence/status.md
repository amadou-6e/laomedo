# Develop integration checkpoint, 12 November 2026

Production merge d3d06e3aa624beae0968d3d8824d9bfabf47a573 integrates develop6077e79a into reviewed8fe9e364. Test binding corrections f38e4b70; docs-only97ea2c3c. Canonical specs PR403 merged at3d6ff82338b32d920ab044f3510fc8d044db3501 after independent review and validation.

All five required CI checks pass atf38e4b70. Exact totals in ci-final-totals.txt:14interface tests,701Docker-boundary tests/28skips;1373installed-wheel tests/260skips on Python3.10 and3.13. Hosted run43195814745. Frontend overlay applies to upstreamfec71dca901949c09ed4d63315804337cd2eb13d; actual Vite build succeeds, five selected Jest suites33tests pass. Windows Jest testMatch escaped the hidden .tools path; an ignored testRegex configuration fixes discovery without changing production config.

Optional-runtime complete suite atd3:1590passes/13skips/7failures. Stale binding/namespace corrections pass54targeted tests/32subtests and4real-Graph stage controls. Final complete optional-runtime rerun at97ea2c3c reports1,595passes,13skips and1,805passing subtests in387.39seconds, with no failure summary. PowerShell reported wrapper exit1 after redirected native stderr warnings; a separate stderr control returns native_exit0 with one PowerShell error record. Independent hosted test jobs exit successfully. No failed test is hidden by the wrapper result.

## Review status

Core packet1: INCOMPLETE, no confirmed findings in the read portions; core-review-verdict.md records actual coverage. Private Graph method question Q1 checked: installed and pinned upstreamGraph define _replace_conditional_exclusions atline1523. Q2's feedback=None case explicitly refuses and is called only on the controlled feedback path; reviewer confirmation pending. Remaining frontend/profile/core, generic imports, tests/maps/docs and combined visual review are fully unreviewed ? reviewer pending.

Next reviewer request ended in a five-hour rate_limit, resetting14:30Europe/Berlin. Its original session/digest/transcript-offset were preserved privately, no duplicate/new reviewer session was started. This is no code verdict.

## View-only evidence

Binary PNGs show the actual combined build. Skill default/Advanced and connectedPrior Run; separatePR capture shows current single-port PRContext and real unconfigured discovery failure. Graphs are copies of current repository node metadata, never execution evidence. No model dispatch, GitHub mutation, copied login or fake model results. Public preview URLs are installation-local and temporary; screenshot state does not establish native execution acceptance. VSCode integrated-browser opening remains unverified because available tools provide no editor command bridge. Independent visual review pending.

Earlier live provider/recovery evidence retains its exact source revisions and limits on exp. No new live model calls were spent for this merge. Owner real-graph acceptance and final integration review remain open. No implementation merge/issue closure authorized.

The four archived develop sources have been verified against every exact byte count and SHA256 in archives/agents-250/20261112/develop-integration/manifest.json. Import-relocation helper and preview harnesses belong only on exp, not production.

Three exact pre-integration test sources were also archived from immutable 8fe9e364 after resolution, retaining the retired legacy-port/migration assertions without putting them back into production. Their manifest states that archival timing explicitly.

Additional recovery/profile frontend checks: four suites, 47 tests pass. Together with the first five suites, 80 selected frontend tests pass. All five final documentation-head CI checks also pass at97ea2c3c (Work Graph43196480251, Black43196480235). No new source changes were made.

Regenerated maintained graph metadata differs in ten non-code locations only: Task accepts Data as well as Message, StrInput replaces MessageTextInput and its inherited trace_as_input flag is absent; serialized connection handles follow the actual current input schema. The two graph invariant digests were refreshed accordingly. Reviewer confirmation of those details remains pending.
