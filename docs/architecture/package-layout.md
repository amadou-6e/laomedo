# Package layout

## Shared host mechanics

[Git](../../src/laomedo/git/README.md) owns host process execution, isolated
environments, repository and working-tree mechanics. Feature owners retain
admission, credential selection, authorization, refs and error translation.
[HTTP](../../src/laomedo/http/README.md) owns neutral redirect refusal. Credential
handlers keep their distinct errors; self-contained components retain their
standard-library copies. Source discovery's separate read-budget process path is
owned by Skills and is outside the shared workspace/transport Git profiles.

GitHubGitTransport, VerifiedGitStage and stage_verified_git accept a
GitCommandRunner through `runner=`. Their previous subprocess-shaped `run=`
callbacks and removed procedural Git helpers are unsupported. Use the current
interfaces and maintained example builders. Install a fresh wheel and run package
checks outside the checkout; discard generated `build/` before rebuilding after
module removals, because stale build output can retain deleted Python files.

Install with `python -m pip install -e .`, or install the wheel. Python 3.10
remains the minimum. Import and launch canonical domain modules directly.
Normal Codex host runners additionally require `python -m pip install -e '.[runner]'`
(or `uv sync --extra runner`) in their launcher environment. This host-only extra
is optional for Langflow/core and stage-worker installations. The pre-PyPI Git
dependency and retained-receipt recovery are described in
[Docker runtime adoption](docker-runtime-adoption.md#local-installation-and-recovery).
The package root contains only `__init__.py` and `_paths.py`; there are no
forwarding modules, import hooks or checkout bridge.

```text
src/laomedo/
|-- activity/
|   |-- agent_activity/
|   |-- claude/
|   |-- opencode/
|   `-- runner/
|-- agents/
|   |-- artifacts/
|   |-- contracts/
|   |-- feedback/
|   |-- handoffs/
|   |-- runtime/
|   |-- workflow/
|   |-- workspace/
|   |-- providers/
|   |   |-- codex/
|   |   |   `-- resources/
|   |   |-- claude/
|   |   `-- opencode/
|   `-- resources/
|-- skills/
|   |-- authoring/
|   |-- ingestion/
|   |-- inspection/
|   |-- operations/
|   |-- registry/
|   |-- sources/
|   |-- workspace/
|   `-- resources/
|-- github/
|   |-- issues/
|   |-- pull_requests/
|   `-- transport/
|       |-- git/
|       `-- rest/
|-- host/
|   |-- credentials/
|   |   |-- codex/
|   |   |   `-- resources/
|   |   |-- claude/
|   |   |-- opencode/
|   |   |-- siwc/
|   |   `-- token/
|   |-- leases/
|   |-- mediation/
|   |-- runner/
|   `-- publication/
|       |-- bundle/
|       |-- handoff/
|       |-- verified/
|       `-- resources/
|-- integrations/
|   `-- langflow/
|       |-- agent/
|       `-- join/
`-- work_graph/
```

Each implementation has one owner. The neutral lifecycle is
`laomedo.agents.runtime.runner.Runner`; Codex execution is
`laomedo.agents.providers.codex.runner.CodexRunner`. Use
`laomedo.skills.registry.store` and `laomedo.activity.agent_activity.capture`.
The activity package exports `ActivityStore`, `capture_for` and `now`;
module patch targets live in their defining modules. Docker build definitions
live in `docker/`; registry documentation is in [the Skills registry guide](../features/skills/registry.md).

Launchers use canonical names:

```text
python -m laomedo.agents.providers.codex.cli ...
python -m laomedo.agents.providers.claude.cli ...
python -m laomedo.host.leases.service_cli serve ...
python -m laomedo.host.managed_service ...
```

The app factory is `laomedo.integrations.langflow.viewer:create_app`.
Credentials and persisted runner/activity state stay outside the package.
Resource bytes, image pins, schemas, request acknowledgement and cleanup
behavior stay unchanged. Resource paths follow their owning package.

## Current examples and historical evidence

Generate maintained graphs through their current builders and component templates.
Personal saved graphs and external launchers are outside compatibility scope;
no user-file migration command is provided. Historical execution evidence retains
its original bytes and revision. Internal ownership/evidence maps remain for
current import checks and explicitly inventoried historical controls.

Validation covers installed discovery, resources and canonical CLIs. Real Agent
and managed-service acceptance are recorded separately from internal tests.

## Cohesion and typed internal data

Package boundaries follow a feature's responsibilities and dependencies, with no
fixed nesting depth. Repeated filename prefixes trigger an ownership review.
Implementation files introduce classes or standalone functions, never both.
Request-handler classes may be nested in their owning server constructor.
Exceptions live in class-only `errors.py`. Helpers that belong to an object become
methods; independent helpers stay in that feature's function-only `utils.py` or a
focused module such as `serialization.py`. `settings.py` owns genuinely shared
constants and mutable locks exactly once. Initializers expose only deliberate
package APIs. Feature imports use explicit module owners; distinct dependencies
must never rebind the same module alias.

Use `settings.py`, not `constants.py`. Externally supplied feature configuration
lives in a feature-owned Pydantic `Settings` object in that file, constructed at
the point of use. Preserve existing environment names, empty/missing semantics
and exact `"1"` flags. Do not read dotenv files or secret directories implicitly.
Token file paths may be settings; credential values must not become settings
fields, logs or serialized configuration. Child-process environment allowlists,
dynamic credential lookups and the standard-library-only Git helper retain their
explicit boundary handling.

Fixed protocol values, image and integrity pins, safety bounds and shared locks
remain module-owned values, never environment fields. General domain payloads
remain in `models.py`; configuration is the explicit `settings.py` exception.
Domain exceptions document their meaning and outcome guarantees, expose the
stable `code`, and retain `str(error) == code` and existing inheritance. A
specialized exception may inherit its constructor, but must state its distinct
contract. Recovery and user-facing explanations remain in the shared error
catalogue; an internal code is not a human-readable error message.

Recurring values travel as canonical Pydantic models in the feature's `models.py`:

| Owner | Models and purpose |
| --- | --- |
| agents/runtime | RuntimeBinding groups provider-owned public record metadata |
| agents/contracts | RunnerRequest groups endpoint, payload and method; its projection preserves saved component HTTP interfaces |
| work_graph | WorkItem, Dependency and GraphSnapshot retain immutable source identity, ordering and snapshot hashes |
| skills/operations | FileEdit, SkillProposal and EditorProvenance carry a multi-file edit and authenticated editor context |
| host/publication/verified | VerifiedStage carries the immutable verified bundle and its provenance |
| host/leases | ContainerIdentity carries exact name, run ID and a secret launch token |
| activity/agent_activity | CaptureIdentity carries graph provenance; ActivityInvocation replaces the anonymous store/invocation tuple |

Models own validation, constructors and explicit projections. HTTP/provider JSON
and persisted records retain their existing fields and identities. Strict models
do not coerce invalid values. Secret-bearing models hide values in representations
and validation text; only the named private registration projection extracts a
lease capability. Model construction never replaces host authorization checks.
The standalone Git credential helper remains stdlib-only.

Current typed interfaces require `ContainerIdentity` for container cleanup,
`CaptureIdentity` for `ActivityStore.start`, and `ActivityInvocation` from
`capture_for`, with `.store` and `.invocation_id`. Historical execution records
are retained without rewriting.

Structural checks reject mixed class/function files, module/package shadowing and
conflicting module aliases. Regression checks preserve model serialization,
existing snapshot bytes/hashes, operation error codes and secret redaction. Error
catalogue checks follow feature error producers after extraction. Installed-wheel,
pinned-stage-image and real graph evidence remain separate from internal tests.

## Provider-neutral Agent boundary

The shared `Runner` is a template-method lifecycle, not a default Codex provider.
It owns private state, durable request identity and acknowledgement, workspace
preparation, immutable skill/artifact inputs and host authorization orchestration.
Codex, Claude and OpenCode extend it directly. They own their constructors,
request policy, model discovery/cache, native execution, resume binding,
pre-dispatch authentication, cancellation and exact restart cleanup.
`RuntimeBinding` in `agents/runtime/models.py` groups the public record fields;
it never carries an access token. Credential identity metadata is distinct from
login material. The record key set remains stable, including explicit nulls.
OpenCode prepared records now report its own CLI and `opencode_http` mode, with
null image/profile/config fields, rather than inherited Codex metadata. Historical
records remain readable; the migration does not rewrite execution history.

The shared HTTP server delegates editor refresh and resume extensions to provider
hooks. Shared runtime code imports neither concrete providers nor credential
implementations. Closed external provider IDs for handoff/artifact validation
belong to the contracts vocabulary, not a default-provider switch.

Mediated GitHub eligibility is explicit: Codex enables it only with its supervised,
non-split execution path. Claude remains ineligible through the shared preparation
path. OpenCode now refuses this path before binding a grant: its former inherited
supervision flag did not implement mediated execution. Existing
`mediated_lease_required` behavior identifies the refusal. This does not enable a
new remote-write capability for either provider.

Graph components keep their public names and ports. Their shared implementation
lives in `integrations/langflow/agent/component.py`, imported by the installed
package, so no additional base node is exposed by the component category loader.
Concrete adapters declare capabilities instead of the common component choosing
behavior by node name. Use current provider-specific templates and regenerate
exports when current dependency metadata is needed. Current source templates are
distinct from historical execution evidence.

Issue #205 covers this boundary. General helper decomposition, cross-feature HTTP/
Git ownership, mediation server extraction and frontend feature directories remain
separate follow-ups (#206?#210).

Concrete Codex components reject stale subclass inheritance before model discovery,
bridge selection or dispatch with `agent_component_migration_required`. This
leaf-adapter check prevents unsupported subclasses from silently routing through
Codex configuration; use the provider-specific current adapter.
OpenCode owns its worker image pin independently in its settings. It initially uses
the same reviewed sandbox bytes as Codex, without importing Codex configuration.
