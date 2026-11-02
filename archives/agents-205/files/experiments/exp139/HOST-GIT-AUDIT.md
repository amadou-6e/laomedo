# Recovery host Git audit, before configuration activation

This is an audit of the proposed recovery path, not activation approval. All
services are stopped and the original 1/4 ledger remains unchanged.

| Host operation | Source | Agent configuration exposure |
| --- | --- | --- |
| Initial checkout cloning | `laomedo/git_workspace.py:prepare_git_workspace` | Source is the trusted clean baseline, not a previous agent workspace; source-side fsmonitor/hooks are overridden and remotes removed |
| Remote installation/check | `laomedo/agent_cli.py:configure_remote` | Isolated Git environment, explicit fsmonitor=false and empty hooks directory; only config lookup/remote setup, no status/add/checkout/diff/fetch against the workspace |
| Skill verification | `laomedo/workspace_skills.py:verify` | Reads filesystem metadata, skill bytes and exclude bytes; no Git subprocess |
| Working snapshot/hash | `laomedo/local_runner.py:_hash_tree`, `_copy_tree` | Filesystem reads/copy with root `.git` omitted; no Git subprocess or filters |
| Bundle freezing | `laomedo/bundle_ingest.py:freeze_run_bundle` | Copies the fixed bounded bundle bytes; no Git subprocess or agent-selected host repository path |
| Bundle verification | `laomedo/bundle_stage.py:verify_frozen_bundle` | Credential-free pinned container, private frozen bundle and trusted baseline; no agent `.git/config` or hooks mounted |
| Artifact classification and push | `laomedo/verified_git_stage.py:stage_verified_git`, `github_git_transport.py` | Imports verified bundle into a fresh independent bare object store; never copies agent repo config/hooks; exact report uses show and diff with --no-ext-diff/--no-textconv |

The proposed regression poisons fsmonitor, hooks, clean/smudge filters, diff
driver and credential helper settings. An intentionally unsafe host `git status`
first proves the fixture executes by creating a marker. The marker is then
removed; remote setup, filesystem hashing and snapshot copy must not recreate
it, and the snapshot must not contain `.git`. The test is credential-free and
uses only disposable local files. It does not prove arbitrary Git commands safe.

Recovery must additionally refuse resume rather than pass an agent-mutated
workspace back through another invocation. Host case selection must preserve
the mediated supervisor for success, and use a distinct ordinary supervisor
only for no-grant cases. The later recovery implementation tests are present in
`tests/test_live_workgraph_bindings.py`; the original audit predates them.
An agent edit to `.git/info/exclude` must still fail the immutable skill-exclusion
check. Keep these gates and independent review before any permission activation.
