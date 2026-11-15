# Real Playwright MCP acceptance

Implementation: ead50c23865b3d2e19bfb2eab976f3bc5947d062.
Official package: @playwright/mcp@0.0.85, native STDIO connection.
Browser: installed Google Chrome, headless, isolated profile.
Provider: Codex gpt-6-luna, low reasoning.

The maintained graph builder connected native MCP Toolset to Agent MCP Tools.
Only browser_navigate, browser_click and browser_snapshot were selected at dispatch.
The agent was given a loopback page URL but not its random result value.
The page initially said Not revealed; clicking Reveal result exposed the random value.
The actual Chrome request reached the page server. The run completed and returned
the exact expected value. The recorded manifest contained three tools.

Run: 997be818-f729-4b61-a546-e8870574f870.
Graph: 1c9d9337-fc0a-4450-9fbd-a08f8002a0fe on owned preview port 17880.
The graph rendered in the owner's shared integrated browser through CoBrowse.

Limits: single fresh Codex run, local page, no authenticated browser or public-site
workflow; not resume/cancellation or other-provider Playwright acceptance.
The page server stopped after the test, so this saved graph requires a new page
server/task URL before replay. Chrome was isolated from the owner's browsing data.
No production code changed. New evidence has not yet received Claude review.

An initial registration using an absolute npx.cmd path was rejected with HTTP 422
before dispatch; the supported npx executable name succeeded without policy changes.
