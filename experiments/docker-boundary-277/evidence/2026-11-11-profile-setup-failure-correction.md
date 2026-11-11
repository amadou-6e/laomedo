# Complete profile setup failure protection - 2026-11-11

Production0fdacaa78 unchanged. A reviewer focused recheck verified the new wrong-endpoint running-state assertion and the Codex state-derived profile cleanup, but found the OpenCode profile could still remain if setup failed before entering the inner cleanup scope. This corrects the prior note's overbroad claim of complete early-failure coverage; it is not a production Agent defect.

The harness now establishes its outer try/finally before Git/workspace setup or any profile/credential write. OpenCode profile deletion runs in that outer finally, requires no Docker client and therefore also runs if profile writing, Docker connection, image admission or sentinel startup fails. Codex cleanup remains inside the client scope; a Codex profile cannot be created until the child starts within that scope. Success is recorded only after all Docker/context teardown succeeds. If cleanup itself fails, the experiment fails and retains its owned evidence instead of discarding uncertain receipts or reporting success.

profile_failure_acceptance.py uses a stubbed Console bootstrap returning SYNTHETIC-NO-CREDENTIAL, and deliberately fails after auth writing at three setup phases. No host credentials are read, no model is called, and no Docker resource is created by these phase controls; the earlier separate empty-volume helper check covers actual Docker-volume deletion. The real Windows private-directory policy and real filesystem writes/deletion are used. Failure directories remain until the control verifies profile absence, then their exact generated TEMP paths are checked and removed.

```json
{"stage": "profile-write", "model_prompts": 0, "synthetic_auth_written_before_failure": true, "injected_failure_observed": true, "private_profile_removed": true, "failure_directory_retained": true, "cleanup_reported": true}
{"stage": "docker-open", "model_prompts": 0, "synthetic_auth_written_before_failure": true, "injected_failure_observed": true, "private_profile_removed": true, "failure_directory_retained": true, "cleanup_reported": true}
{"stage": "sentinel-start", "model_prompts": 0, "synthetic_auth_written_before_failure": true, "injected_failure_observed": true, "private_profile_removed": true, "failure_directory_retained": true, "cleanup_reported": true}
```

These are synthetic-data failure controls, not native provider acceptance. Earlier successful model/restart observations retain their original revisions. No inference was repeated merely to check teardown. Focused reviewer recheck pending for the complete setup correction. The original HF IDs described OpenCode credential retention as HF03 and Codex early failure as HF04; the preceding recheck swapped those labels while describing the mechanisms. Track by the original mechanism/ID pair, without changing historical text.
