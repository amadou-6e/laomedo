# Native profile browser checks, 2026-11-10

Sources: profile tracking `7bfeffb0`, logout coordination `ce19d9a5`.
Fresh pinned frontend `fec71dca` with task overlay, built using Node22.23.3.
Only a separate task-owned Edge profile and synthetic QA PINs were used.

Observed actual app behavior: profile creation201 and upstream login200; session
restoration on reload and browser restart; community link opened a popup without
the unsupported optional tracking PATCH. An injected logout network abort stayed
unconfirmed and Check current profile restored the live session.

The first two-tab switch exposed a missing broadcast after upstream logout
cleanup unmounted the menu. After `ce19d9a5`, switch returned both tabs to the
picker. Wrong PIN checks returned four401 responses then a real429, cleared the
PIN, and displayed/disabled controls for the server-provided60second delay.

Screenshots and runtime logs are outside Git in the task readiness directory.
TypeScript remains failing with652 diagnostic lines, none in the profile files;
the same count was present in the pinned baseline. Production build succeeds.
These observations do not establish all profile acceptance, owner approval or
Claude review of the latest correction; those remain pending.
