# Proposed EXP-139 local configuration

This file describes a draft. No activation is implied by committing it.

The disposable composition uses the landed `LocalRunner`, original independent
lease supervisor, mediation journal, native Git wrapper, pinned skill, output
precheck, Output Contract and trusted Draft PR Publisher. It adds an experiment
binding that matches exact graph requests on the host. The graph cannot supply
or mint a GitHub grant. Same-user local grants remain run-scoping controls, not
a human-authorization boundary.

## Concrete change

- Prepare a new private directory outside every Git checkout, under the Windows
  temporary directory, named `laomedo-exp139-20261011-a`. Its `config.json` and
  `preparation.json` record exact input pins. Do not mount the whole directory.
- Use `.env` key `GH_LAOMEDO` only through `HostTokenConnection` on the host, for
  `ga84jog/laomedo-exp104-disposable-20261007`. Replacing that key invalidates the
  connection. No ambient personal `gh` login or credential fallback.
- Read one existing issue and the default-branch baseline through that connection
  during preparation. No issue creation or edit. The task writes a fixed report
  identifying the frozen issue; arbitrary issue instructions are not executed.
- Start `runtime services` as an independent hidden host process. It serves the
  mediator and lease supervisor on dynamically selected loopback ports and
  verifies one immutable Git bundle in a credential-free pinned Docker stage.
- Start `runtime runner` as another hidden host process on `127.0.0.1:8779`.
  Existing services and saved flows are untouched. Four submitted turns total,
  original permissions, existing Codex subscription-login volume, Codex 0.159.2,
  Git image `sha256:eceda79a349c46a8afd6fb271e92b979f872ca67cbdf228fde6dee0856481e78`.
- The success run gets a 600-second original handoff deadline and exactly the
  `git_push` / `pr_create` operations for branch `exp139-20261011-a`. A durable
  host budget admits at most one attempted push and one attempted draft PR.
  Unknown attempts are not repeated. The agent PR lane is refused; only the
  controller's `publication_pending` phase may create the PR.
- The report's exact path and bytes are checked from independently verified Git
  objects before push and again before publisher handoff. No other changed file,
  including workflow files, is accepted.
- Execute each exported/imported graph in the pinned Langflow 1.12.3 image. Mount
  reviewed implementation source and graph input read-only, and only the local
  runner API token as a single secret file. Never mount host services, GitHub
  credentials, the private verified stage or Codex login into Langflow.
- The controller/agent connection retains the currently accepted bounded local
  credential custody. This does not establish hosted safety or a new auth flow.
- Run the cases allocated in AMENDMENT-01.md. Remove only exact owned graph/test
  containers and stop only these new host processes afterwards. Keep workspaces,
  partial traces and the approved remote branch/draft PR for review.

## Admission and execution

`python -m experiments.exp139.prepare --state <new-private-directory> --token-file
<workspace>/.env` prepares inputs and drafts; it never starts services or a model.
The configuration and exact-source review must be recorded before activation.

After approval, create `manifest.json` with every reviewed source file hash and
the config/baseline/graph input hashes. The host-only `activation.json` binds that
manifest and exact source commit to the configuration approval and reviewer
verdict. Both runtime roles refuse missing or mismatched records. Do not hash
credential values. This is a recorded local operator procedure, not protection
against a malicious process running under the same Windows identity.

Activation commands, each in an independent hidden process:

```text
python -m experiments.exp139.runtime services --state <new-private-directory>
python -m experiments.exp139.runtime runner --state <new-private-directory>
```

Then execute `experiments/exp139/run_flow.py` in the pinned image with one frozen
case graph. Persist the campaign turn ledger before any native `turn/start`.
Read back the PR and its report file using the selected connection, verify the
exact report digest, and scan all proposed evidence for credential bytes without
printing values. Record unexecuted live cases and every unknown honestly.
