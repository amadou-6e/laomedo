# Go allowance layout verification

Production source: Laomedo feat/313 at be13a9d5b. This exp-only harness exercised
actual saved-account quota routes on the isolated preview port17888. It submitted
zero model prompts and used no mocked HTTP responses. OpenCode Go returned its
real403 safe projection. Codex returned real five-hour100%/weekly66% observations.

The harness uses the owner's previously authorized local PIN in memory, without
exporting cookies, credentials, session storage or login state. Browser call logs
are suppressed on failure because they can contain filled PIN values. Screenshots
and result metadata remain ignored local artifacts; no runtime files are tracked.

Observed in a fresh Chromium1248 headless context at360x1000, light theme:
Go pane client/scroll widths360/360; Codex meter group width294, scroll/client294,
two actual windows, heading flex-direction column. No horizontal quota overflow.
Both reads retained existing connections. This does not establish successful Go
numeric allowance access: the saved key was refused. Wide shared UI was checked
separately in the owner's VS Code Laomedo Provider session.

Run from this experiment checkout with Node22 and the target workspace path:
`node experiments/go-quota-313/validate-layout.mjs C:/CodeWorkspace/laomedo`.
This requires the owning task's installed Playwright, browser and running preview;
normal production tests never import or depend on it.
