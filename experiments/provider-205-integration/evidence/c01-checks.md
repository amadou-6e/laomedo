# Installer correction checks

Production correction2a8a764218117674977e39455ea6c305ebc8614b; tests-only direct-call cleanup3150ce03d6a6164180abd0f1061c526170f662d9.

- `python -m unittest test_langflow.test_profile_overlay test_agents.test_architecture.test_provider_contracts -v`:16tests pass.
- After direct-call cleanup, `python -m unittest test_langflow.test_profile_overlay -v`:2tests pass. Four negative anchor cases check unchanged filesystem state and absence of new profile assets; the positive case checks route/session binding and exact copied asset bytes.
- PinnedBlack26.10.1:894maintained files pass; later test-only edit and installer pass no-cache focused check.
- `profile_overlay_validation.py` compares pre-correction and corrected profile stages using actual source files from pinned upstreamfec71dca901949c09ed4d63315804337cd2eb13d:17generated files byte-identical. It invokes no model, browser, authentication or server. Result in c01-pinned-output.json.

The local logs remain ignored; no credentials or runtime state are published. Hosted checks for3150ce03 are running at this evidence checkpoint. C01focused reviewer recheck remains pending because the existingreviewer hit quota, reset19:30BerlinNov12. These checks are not independent review or live agent acceptance.
