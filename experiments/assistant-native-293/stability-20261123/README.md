# Three-provider chat stability acceptance — 2026-11-23

The requested final batch passed **20/20 distinct real conversations**: 7 Codex,
7 Claude and 6 OpenCode. These were normal saved-profile chats through the real
application UI and provider runtimes, without HTTP mocks or injected provider
credentials. The harness logged into the existing profile normally; credentials,
cookies, raw transcripts, conversation IDs and screenshots remain private.

## Exact scope and evidence

- Functional implementation: `8325a10c6d9a468ea1daa3f5dfbc39b327a92076`.
- Final layout: `3f10cb5842e43b417dd015bd549ccc54218a3a2a`; the later difference
  changes only separator CSS and documentation, not dispatch or lifecycle code.
- Harness at batch launch: `5e1d9ec`, `../stability.mjs`, seed `333244545`.
- Batch F: 14:28:39–14:40:28 UTC, November 23. Up to one conversation per provider
  ran concurrently. The served application build stayed unchanged throughout.
- [Sanitized results](results.json) record every case, model, selected operation,
  retained message/receipt audit, and Send-readiness checks. The private source
  report's SHA-256 is retained there for exact local provenance.
- [UI checks](ui-checks.json) record the separate actual-browser checks against
  the final layout, including scroll-free pagination, keyboard selection,
  OpenCode model labels, rail dragging/collapse, and settled theme colors.

Each conversation sent a fresh validation marker, randomly selected one actually
executable native command from its observed catalog, recalled the original marker
in a follow-up, reloaded the browser and sent another prompt. After **each** terminal
operation, the harness entered a nonempty unsent draft and required Send to become
enabled. The read-only audit then confirmed 80 retained completed messages,
20 completed native action receipts and one stable run binding per conversation.
There were 80 successful Send-readiness checks. No uncertain operation was replayed
automatically.

| Provider | Conversations | Selected native commands |
| --- | ---: | --- |
| Codex | 7 | `review`, `status`, `mcp`, `$skill-creator` |
| Claude | 7 | `mcp`, `context`, `claude-api`, `usage` |
| OpenCode | 6 | `init`, `review` |

This is the requested bounded stability sample, not exhaustive coverage of every
offered command or every model. Account/logout/rename application navigation and
disabled native entries were excluded from random native-command selection.
Codex used `gpt-6.1-sol`, Claude `sonnet`, and OpenCode `opencode-go/gpt-6-luna`.
Native review/init target the existing isolated scratch/controller arrangement,
not the user's repository. Skill-creator dispatch does not itself establish
helper-backed skill-validation acceptance.

## Defects found and corrected

1. A definite overlapping-request refusal left a client error that permanently
   gated an otherwise observed idle conversation. Definite refusal no longer
   blocks the next message; uncertainty, active-run and observation fences remain.
2. Login revalidation dropped the conversation query on reload. The upstream
   guard now preserves the encoded full same-site path, query and fragment.
3. OpenCode's worker hit Git's dubious-ownership guard on the host-owned `/draft`
   mount. Only that fixed mount is now trusted through process configuration;
   no credentials, wildcard trust or network access were added. A real
   credential-free worker probe passed status/diff checks and confirmed the
   exact trust value. The final sample passed native `review` repeatedly.
4. The shared resize/collapse rail initially captured pointer events on its
   parent, losing collapse clicks. Capture now belongs to its existing button.
5. Automatic history needed a visible sentinel for pages that cannot scroll,
   and request identity to clear loading correctly across profile changes.

Feedback also produced monochrome provider marks replacing text in metadata,
faint rules between stacked conversations, hidden OpenCode Go display prefixes,
automatic earlier-history loading, background spinners, and Enter selecting the
first usable command/skill. Enter waits for discovery rather than sending a
partial command as prose. The final UI checks passed after the row-divider change.

## Earlier batches are not acceptance passes

| Batch | Outcome | Reason |
| --- | --- | --- |
| A | Stopped | Observer misclassified a transient mixed idle/reserved read; the same attempt subsequently completed. Observer corrected without replay. |
| B/C | Stopped | Login return discarded the conversation query. Fixed before final acceptance. |
| D | Stopped | OpenCode `review` encountered Git ownership rejection. The model recovered, but the existing strict error predicate correctly retained failure. Trust scope fixed, not error predicate weakened. |
| E | 8 passed, then stopped | An in-place local frontend rebuild removed served `index.html` during a reload. This deployment interruption was excluded. |
| F | **20/20 passed** | Uninterrupted fixed build; all command, follow-up, reload and Send-readiness checks passed. |

Further preview builds were staged separately. The row-divider update was
published after F by atomically replacing the HTML entry only after assets were
available, retaining old hashed assets for existing tabs. Probe code and evidence
stay on `exp`; production tests and runners do not depend on them.
