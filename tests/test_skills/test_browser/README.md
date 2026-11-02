# Skill browser controls

`files.cjs` checks file navigation and read-only rendering; `sources.cjs` checks
source discovery and immutable selection. Both accept an explicit existing
fixture manifest as their first argument. They retain their original prerequisites
and assertions, and are internal fixture controls rather than real-agent or
owner-acceptance evidence. Neither script runs during Python discovery.

```powershell
node tests/test_skills/test_browser/files.cjs <fixture-manifest.json>
node tests/test_skills/test_browser/sources.cjs <fixture-manifest.json>
```
