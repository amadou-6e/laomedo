# Issue 146: Docker Skill Draft feasibility

This experiment tests the Docker execution route against the same versioned
Skill Draft policy and synthetic skill used by [issue #122](../122/README.md).
It is the code and sanitized-evidence deliverable for
[specs issue #146](https://github.com/amadou-6e/specs/issues/146). No canonical
skill was promoted or changed.

## Result

On 2026-09-30, a Codex agent in Docker edited a disposable `SKILL.md` and
invoked the pinned `boundary-check.js` validator. Its completed command event
reported an attempt to write `/store/sentinel.txt`, exit code 2, and an OS
denial. The synthetic store was mounted **writable** in Docker as a positive
control, yet its host sentinel remained unchanged. The agent then resumed the
same native thread after app-server restart against a fresh mount restored
from the pinned post-run candidate. A completed read command returned the
post-run example line. The canonical skill stayed unchanged.

The raw agent workspace contained three empty Codex-created directories:
`.agents`, `.codex`, and `.git`. A credential-free diagnostic showed that
`thread/start` creates `.codex` and `.git`; the agent turn left `.agents` too.
`materialize_candidate.py` preserves the raw workspace, permits only those
exact directories when empty, and copies the approved `SKILL.md` to a separate
candidate. It rejects a nonempty runtime directory or any extra path. The
candidate has only `SKILL.md`, a distinct hash and patch, zero validation
violations, and a passing fixed case. This is review eligibility, not automatic
promotion.

| Check | Observed result |
| --- | --- |
| Draft edit and policy validation | Pass: only `SKILL.md` changed in the pinned candidate |
| Agent-originated forbidden write | Pass: command event, exact synthetic target, exit 2, OS denial, unchanged host sentinel |
| Canonical and sibling writes | Pass: read-only canonical mount and Codex profile denied writes; writable synthetic store positive control succeeded outside Codex |
| Path traversal and escaping symlink | Pass: both denied by Codex; the symlink was also rejected by inventory |
| Forbidden script or file type | Pass: OS allowed a synthetic script in the draft, and policy validation rejected it |
| Partial failure and timeout | Pass: draft partials persisted as evidence and were marked ineligible |
| Missing or corrupt snapshot; concurrent base change | Pass: restore or promotion eligibility refused without overwriting the draft or canonical skill |
| Persistent resume | Pass: same native thread, restored candidate hash, observed read of the post-run line |
| Network controls | Pass for the tested paths: direct loopback and external connections succeeded; Codex sandbox denied loopback with `EPERM` and external DNS with `EAI_AGAIN`. App-server `command/exec` also denied external access. |
| Credential read | Pass for the exact path: app-server `command/exec` could not read the private volume's `auth.json`; the personal Codex profile was not mounted |

The direct network controls used a credential-free container. Docker bridge
networking allowed the controller to reach the model, while the named Codex
permission profile requested no agent-command network access. These probes
verify the tested loopback and external paths, not every protocol or a hosted
multi-user network policy. The local engine reported Docker 27.3.1; its
outer security configuration is not a substitute for reviewing the complete
container threat model. [Codex's Linux sandbox](https://github.com/openai/codex/blob/main/codex-rs/linux-sandbox/README.md)
uses Bubblewrap for restricted filesystem execution, and
[permission profiles](https://learn.chatgpt.com/docs/permissions) define the
named path and network rules. [Docker bind mounts](https://docs.docker.com/engine/storage/bind-mounts/)
are writable by default, so the canonical mount is explicitly read-only.

## Reproduce

Observed host: Windows with Docker Desktop Linux engine 27.3.1 and Python
3.12.10. The scripts use Python standard library only. The image in
`../122/container/Dockerfile` pins the Node base digest and Codex CLI 0.159.2.
The Docker runner uses UID 10001, drops all capabilities, sets
`no-new-privileges`, and does not mount the Docker socket or personal profile.

From the Laomedo repository root, these tests use no login or model turn:

```powershell
docker build --tag laomedo-codex-boundary:0.159.2 experiments/feasibility/122/container
python experiments/feasibility/docker-skill-draft/probe_filesystem.py
python experiments/feasibility/docker-skill-draft/probe_network.py
python -m unittest discover -s experiments/feasibility/docker-skill-draft -p 'test_*.py' -v
```

`probe_appserver_network.py` makes no model call but requires the existing
private Docker runner volume. `probe_agent_boundary.py` and
`probe_agent_resume.py` use the persistent single-user ChatGPT handoff and a
separate Docker-route turn ledger. They are one-time historical probes and
fail closed if the ledger is at a different count. Do not reset that ledger or
make another login copy to rerun them. The original #122 ledger remains 7/7;
the Docker-route ledger now records **4/6** submitted turns, including two
earlier turns documented in `../122/README.md`. No further turn is needed for
this feasibility result.

`filesystem-observations.json`, `network-observations.json`,
`appserver-network-observations.json`, and `model-observations.json` contain
only synthetic results and whitelisted identifiers, hashes, usage counters,
and pass/fail facts. `sanitize_model_observations.py` produces the last file
from private local summaries. Raw app-server streams, session files, and the
login remain in private state outside Git. A comparison after turn 4 found the
Docker login copy still byte-identical to the isolated #120 source; future
refresh-token rotation remains a risk.

## Decision

**Go for a bounded, single-user local Docker Skill Draft prototype** with the
tested mounts, named Codex permission profile, exact credential deny path,
candidate materialization, and fail-closed validation. **No-go for hosted or
multi-user execution** on this spike alone. Production credential provisioning,
refresh, rotation, and revocation belong to [#129](https://github.com/amadou-6e/specs/issues/129).
The network tests cover specific paths, and a production runner still needs
a broader threat review, operational policy, and retained access controls.
