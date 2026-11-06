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

`canvas_refresh.cjs <owned-loopback-flow-url> <skill-node-id>` holds and releases
an actual graph-build response to check that canvas query updates do not unmount
an open workspace. It is a controlled pass-through regression, with no fixture
responses or model dispatch, and is supporting evidence rather than acceptance.
The file viewer control asserts descriptive refusals without futile reload,
safe unknown-failure fallback and retry of the same read without private bodies.
