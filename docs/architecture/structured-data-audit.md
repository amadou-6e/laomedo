# Structured-data audit

Python baseline: `a9317f61ce0376ead778802d3fd394fa127fe8a2`. Locations below refer to that immutable
baseline, not line numbers after formatting or future module moves.

The scan inspected every tracked Python file, selecting dictionary literals
or `dict(...)` definitions with at least six entries or twenty physical lines.
This is an inventory heuristic, not an instruction to turn every mapping into
a class. Fixed records with related fields use canonical feature-owned models;
dynamic maps, dispatch tables, native raw observations and existing serializers
retain their appropriate representation. New-write models do not replace
historical readers. Secret projections name their private destination.

Python files by scope: `{"components": 12, "docker": 1, "examples": 41, "experiments": 199, "production": 289, "tests": 161, "tools": 4}`.
Large blocks by scope: `{"examples": 32, "experiments": 201, "production": 84, "tests": 87}`.
Python parse errors: `0`.

47 production constructors migrated or reused canonical models;
37 retained with the explicit reasons below.

## Production dispositions

| Baseline location / owner | Disposition | Reason |
| --- | --- | --- |
| `src/laomedo/agents/activity/projection.py:361` `project` | Retain | Native Activity read projection aggregates heterogeneous retained events; preserve missing/unknown values and raw event payloads. Not a mutable lifecycle schema. |
| `src/laomedo/agents/activity/projection.py:154` `project` | Retain | Native Activity item frame keeps the original heterogeneous native item unchanged; no new strict event reader. |
| `src/laomedo/agents/activity/projection.py:248` `project` | Retain | Native usage-point projection combines provider-specific optional observations, not an admitted execution record. |
| `src/laomedo/agents/agents/base/acp/models.py:31` `AcpTurn.tool_calls` | Retain | Already a serializer method on canonical AcpTurn; nested native input/output remains provider-owned. |
| `src/laomedo/agents/agents/base/agent.py:301` `BaseAgent._materialize` | Model / reuse | Reuse AgentSkillBinding for installed skill evidence; serialize only for existing workspace helpers. |
| `src/laomedo/agents/agents/base/agent.py:434` `BaseAgent._prepare` | Model / reuse | PreparedRunRecord with canonical workspace/runtime/skill/artifact/handoff values. |
| `src/laomedo/agents/agents/base/agent.py:590` `BaseAgent.select_artifacts` | Model / reuse | Reuse ArtifactReference for validated selected-file evidence. |
| `src/laomedo/agents/agents/claude/activity/telemetry.py:55` `ClaudeTelemetry.__init__` | Model / reuse | ClaudeTelemetryEnvironment owns the private native environment projection. |
| `src/laomedo/agents/agents/claude/agent.py:291` `ClaudeAgent.preflight` | Retain | One provider readiness projection over observed runtime/catalog/tool values; canonical RuntimeBinding already owns persisted identity. No duplicate readiness domain. |
| `src/laomedo/agents/agents/claude/agent.py:1003` `ClaudeAgent._execute` | Model / reuse | Shared ActivityAttemptRecord constructs initial attempt observations. |
| `src/laomedo/agents/agents/claude/agent.py:1102` `ClaudeAgent._execute` | Retain | Provider-native turn receipt retains observed status and optional native session evidence; preserve partial observations. |
| `src/laomedo/agents/agents/claude/agent.py:1082` `ClaudeAgent._execute` | Retain | Claude-native result evidence deliberately preserves provider raw fields/unknowns, distinct from safe public run references. |
| `src/laomedo/agents/agents/claude/models.py:26` `ClaudePolicy.sdk_options` | Retain | Already the explicit native serializer on canonical ClaudePolicy. |
| `src/laomedo/agents/agents/codex/agent.py:387` `CodexAgent._open_server` | Model / reuse | Construct existing CodexLaunch directly instead of an intermediate definition dictionary. |
| `src/laomedo/agents/agents/codex/agent.py:512` `CodexAgent._preflight` | Retain | One provider readiness projection over observed model/config/permission checks; keep admission order and unknown evidence. |
| `src/laomedo/agents/agents/codex/agent.py:670` `CodexAgent._execute_acp` | Model / reuse | Shared ActivityAttemptRecord constructs initial attempt observations. |
| `src/laomedo/agents/agents/codex/agent.py:1037` `CodexAgent._execute_acp` | Retain | Codex-native completion receipt keeps partial interrupt/command/native-error evidence; not a second run-state model. |
| `src/laomedo/agents/agents/codex/utils.py:50` `_native_error_summary` | Retain | Safe summary over heterogeneous raw errors with dynamic category/status collections; retain native observations rather than enforce new event admission. |
| `src/laomedo/agents/agents/codex/utils.py:149` `_command_summary` | Retain | Mutable native command evidence is filled from out-of-order events; unknown completion is deliberate. No strict historical reader added. |
| `src/laomedo/agents/agents/opencode/activity/projection.py:386` `project` | Retain | OpenCode-native Activity projection aggregates heterogeneous records and partial telemetry; keep raw evidence shape. |
| `src/laomedo/agents/agents/opencode/activity/projection.py:414` `estimate_native` | Retain | Native cost provenance metadata changes shape with catalog source/tier and is not a billing record; preserve unknown estimates. |
| `src/laomedo/agents/agents/opencode/activity/projection.py:212` `project` | Retain | Native tool item wrapper retains the original provider item and unknown status evidence. |
| `src/laomedo/agents/agents/opencode/activity/projection.py:281` `project` | Model / reuse | OpenCodeTokenUsage converts admitted native counters to canonical TokenUsage. |
| `src/laomedo/agents/agents/opencode/activity/projection.py:196` `project` | Retain | Native tool frame retains the original item; no new strict native event reader. |
| `src/laomedo/agents/agents/opencode/activity/projection.py:247` `project` | Retain | Native assistant frame retains optional native text/tool payloads without coercion. |
| `src/laomedo/agents/agents/opencode/activity/projection.py:326` `project` | Retain | Native usage/cost point is a partial observation projection, distinct from validated TokenUsage counters. |
| `src/laomedo/agents/agents/opencode/agent.py:326` `OpenCodeAgent._execute` | Model / reuse | Shared ActivityAttemptRecord constructs initial attempt observations. |
| `src/laomedo/agents/agents/opencode/boundary.py:243` `IsolatedOpenCode.__init__` | Model / reuse | OpenCodeRuntimeIdentity groups the retained runtime and credential-binding metadata. |
| `src/laomedo/agents/agents/opencode/boundary.py:388` `IsolatedOpenCode.__init__` | Retain | Fixed native environment policy plus private runtime paths; no externally supplied settings or repeatedly passed definition object. |
| `src/laomedo/agents/agents/opencode/history/models.py:99` `NativeExport.tool_calls` | Retain | Already a serializer method on canonical NativeExport. |
| `src/laomedo/agents/agents/opencode/history/reader.py:293` `HistoryReader.retain` | Retain | Retained native export envelope preserves exact message/history observations and byte provenance; no strict read schema for historical exports. |
| `src/laomedo/agents/agents/opencode/models.py:42` `OpenCodeConfig.to_config` | Retain | Already the explicit native serializer on canonical OpenCodeConfig. |
| `src/laomedo/agents/interface/bridge.py:63` `HttpAgentBridge.fresh_request` | Retain | Exact async request-hash boundary assembled from already-admitted handoff; canonical AgentHandoff/HandoffProvenance own domain structure. Do not duplicate it as a second request model. |
| `src/laomedo/agents/interface/bridge.py:233` `HttpAgentBridge.dispatch` | Model / reuse | AgentDispatchResult preserves the explicit safe bridge result allowlist. |
| `src/laomedo/agents/interface/langflow/component.py:813` `AgentComponent._run_reference` | Model / reuse | AgentRunReference and PrecheckEvidence preserve unknown/null evidence normalization. |
| `src/laomedo/agents/interface/langflow/component.py:935` `AgentComponent.submission_output` | Model / reuse | AgentSubmission owns the routed graph result projection. |
| `src/laomedo/agents/interface/output/utils.py:140` `evaluate` | Retain | JSON Schema type-name to Python-type dispatch table, not a domain record. |
| `src/laomedo/agents/orchestration/controller.py:212` `AgentHandoffController._persist` | Retain | Execution persistence snapshot contains heterogeneous transition/cancel records and caller limits; retain historical journal schema and partial evidence. |
| `src/laomedo/agents/orchestration/utils.py:79` `envelope` | Model / reuse | AgentHandoff with typed source, target, prior, artifacts and provenance. |
| `src/laomedo/github/issues/contract.py:64` `issue_value` | Model / reuse | GitHubIssue owns the normalized value after existing manual admission. |
| `src/laomedo/github/issues/gateway.py:146` `GitHubIssueGateway.execute` | Model / reuse | Shared GitHubOperationIntent/GitHubGrantBinding preserve authenticated hash inputs. |
| `src/laomedo/github/issues/utils.py:57` `_issue` | Retain | Legacy read-only issue context shape is weaker than normalized node GitHubIssue; do not silently replace its admission with the stricter node model. |
| `src/laomedo/github/issues/utils.py:151` `fetch_context` | Retain | Read-only issue/related-PR context projection retains incomplete discovery warnings and optional supplied target; not a normalized node value. |
| `src/laomedo/github/pull_requests/contract.py:49` `pr_value` | Model / reuse | GitHubPullRequest/PullRequestHead own the normalized PR value. |
| `src/laomedo/github/pull_requests/gateway.py:83` `GitHubPRGateway.prepare_feedback` | Model / reuse | PullRequestFeedbackContext constructs new ticket snapshots; old readers unchanged. |
| `src/laomedo/github/pull_requests/gateway.py:283` `GitHubPRGateway.execute` | Model / reuse | Shared GitHubOperationIntent/GitHubGrantBinding preserve authenticated hash inputs. |
| `src/laomedo/github/transport/rest/transport.py:389` `GitHubRestTransport.__call__` | Retain | Narrow external REST result projection; canonical normalization is performed at the node contract boundary, not the transport. |
| `src/laomedo/host/credentials/siwc/connection.py:86` `ChatGPTConnection.begin` | Model / reuse | OAuthAuthorizationRequest owns the private ordered authorization query. |
| `src/laomedo/host/credentials/siwc/connection.py:111` `ChatGPTConnection.begin` | Model / reuse | OAuthAttempt has excluded secrets and an explicit private projection. |
| `src/laomedo/host/credentials/siwc/connection.py:189` `ChatGPTConnection.finish` | Model / reuse | OAuthAccount constructs new admitted account writes; old account reads unchanged. |
| `src/laomedo/host/credentials/siwc/connection.py:153` `ChatGPTConnection.finish` | Model / reuse | OAuthCodeExchange unwraps secrets only for the existing private form encoder. |
| `src/laomedo/host/host_services.py:118` `serve_services` | Model / reuse | Shared MediationServiceRecord preserves optional module-root omission. |
| `src/laomedo/host/leases/grants.py:33` `GrantBook.issue` | Model / reuse | LeaseGrant/GrantWindow/LeaseClock group grant identity and state transitions. |
| `src/laomedo/host/leases/models.py:53` `ContainerIdentity.registration` | Retain | Already an explicit private serializer on canonical ContainerIdentity; tokens excluded from ordinary dumps. |
| `src/laomedo/host/leases/service.py:190` `LeaseService._revoke_and_cleanup` | Model / reuse | LeaseRevocationRecord preserves pre-cleanup unknown/omitted fields. |
| `src/laomedo/host/leases/service.py:216` `LeaseService._revoke_and_cleanup.finish_cleanup` | Model / reuse | LeaseRevocationRecord preserves completed cleanup observations without inference. |
| `src/laomedo/host/leases/service.py:371` `LeaseService._refuse_lease.finish_refusal` | Model / reuse | LeaseRefusalRecord groups observed refusal and cleanup evidence. |
| `src/laomedo/host/managed_service.py:14` `` | Retain | Static service-name to command-line option registry, not an object instance. |
| `src/laomedo/host/mediation/authority.py:250` `RunGrantAuthority.authorize_lease` | Model / reuse | AuthorizedLeaseScope preserves sets, integer target keys and optional branch/base. |
| `src/laomedo/host/mediation/cli.py:121` `main` | Model / reuse | Shared MediationServiceRecord preserves standalone service metadata shape. |
| `src/laomedo/host/publication/bundle/stage.py:247` `_locked_container_stage` | Model / reuse | ContainerStageRecord constructs initial journal; later cleanup mutation stays service-owned. |
| `src/laomedo/host/publication/bundle/stage.py:465` `verify_frozen_bundle` | Model / reuse | BundleVerificationRecord constructs initial journal; readers and outcome policy unchanged. |
| `src/laomedo/host/publication/controller.py:92` `PublicationController.finish_agent` | Retain | Publication-specific seven-field graph output allowlist; deliberately different from ten-field AgentSubmission. Preserve omission and do not merge contracts. |
| `src/laomedo/host/publication/handoff/store.py:145` `HandoffStore.freeze_publication_handoff` | Model / reuse | PullRequestPublicationRequest groups the new draft-publication request. |
| `src/laomedo/host/publication/verified/utils.py:328` `resolve_verified_stage` | Model / reuse | VerifiedStageIdentity owns the exact active/frozen canonical digest preimage. |
| `src/laomedo/host/publication/verifier.py:192` `BundleVerifier.serve` | Retain | Single readiness diagnostic initialized once and mutated by the verifier scan loop; not execution success or publication authority. Historical service readers unchanged. |
| `src/laomedo/host/runner/http/handler.py:143` `RunnerRequestHandler.do_GET` | Retain | Dynamic raw native-event feed allowlist merges heterogeneous accepted event data and current observations; preserve raw payload fidelity. |
| `src/laomedo/integrations/langflow/join/controller.py:87` `LangflowJoinController._snapshot` | Retain | Legacy SQL/journal read projection with nullable/partial lifecycle evidence; no stricter historical reader introduced. |
| `src/laomedo/integrations/langflow/join/server.py:44` `JoinServer.__init__.Handler.presented` | Model / reuse | RunnerStatusRecord keeps the join shape separate from graph run references. |
| `src/laomedo/skills/operations/service.py:381` `SkillOperations.compare` | Model / reuse | SkillComparison and SkillFileChange own current-file comparison values. |
| `src/laomedo/skills/operations/service.py:238` `SkillOperations.apply` | Model / reuse | SkillCommit, EditorProvenance and SkillCommitReceipt preserve exact journal hashes. |
| `src/laomedo/skills/operations/service.py:113` `SkillOperations.prepare` | Model / reuse | SkillCommit and ImportedSkillEditor preserve import commit hashes and omission. |
| `src/laomedo/skills/registry/store.py:264` `SkillStore.freeze_draft` | Model / reuse | FrozenSkillDraft owns reviewed tree, validation and evaluation evidence. |
| `src/laomedo/skills/registry/store.py:88` `SkillStore._store_revision` | Model / reuse | SkillRevision constructs new registry writes; historical readers unchanged. |
| `src/laomedo/skills/registry/store.py:194` `SkillStore.create_draft` | Model / reuse | SkillDraft constructs admitted new draft writes. |
| `src/laomedo/work_graph/__main__.py:108` `main` | Model / reuse | WorkGrantReference keeps limits grouped internally and the CLI receipt flat. |
| `src/laomedo/work_graph/grants.py:126` `LocalGrantAuthority.__call__` | Model / reuse | WorkLaunchGrant/WorkGrantLimits group the safe redeemed grant response. |
| `src/laomedo/work_graph/launch.py:114` `preflight` | Model / reuse | WorkSnapshot owns selected immutable work identity and body digest. |
| `src/laomedo/work_graph/launch.py:122` `preflight` | Model / reuse | WorkLaunchBinding/WorkOverride group selected/current/frozen source evidence. |
| `src/laomedo/work_graph/launch.py:46` `relevant_content_digest` | Model / reuse | RelevantWorkContent owns the canonical selected transitive-content hash preimage. |
| `src/laomedo/work_graph/local_launch.py:54` `launch_local_saved_flow` | Model / reuse | WorkLaunchResult owns the safe local launch summary. |
| `src/laomedo/work_graph/models.py:247` `GraphSnapshot.project` | Retain | Already an explicit projection method on canonical GraphSnapshot, including dynamic filtered indexes. |
| `src/laomedo/work_graph/runs/store.py:963` `WorkflowRunStore.trace_snapshot` | Retain | Legacy SQL/journal trace read projection with partial/recovery evidence; no stricter historical reader introduced. |
| `src/laomedo/work_graph/runs/store.py:699` `WorkflowRunStore.record_runner_terminal` | Retain | Partial transactional lifecycle update over admitted native terminal observations; not a full execution record. |

## Other Python scopes

All components, Docker sources, examples, tools, tests and archived experiments
were included in discovery. Component run-reference/submission construction
delegates to the Agent interface models in production. Other selected blocks
in examples are Langflow graph/component-template JSON projections; graph
schemas and port IDs remain external contracts, not duplicate Pydantic models.
Experiment blocks are historical campaign/configuration/evidence or controls;
test blocks are protocol inputs and deliberately malformed cases. They remain
independent controls rather than recreating expected values through the models
under test. None is a live acceptance result. Maintained Python formatting is
a separate concern governed by the Black policy, including exact sealed-source
exceptions where documented.

## JavaScript and TypeScript

A separate syntax-tree scan inspected 66 tracked JS/TS/MJS/TSX files
and found 50 object blocks meeting the same size heuristic.
Pydantic is a Python contract. Native protocol objects in these adapters remain
JavaScript/TypeScript values; do not create an unvalidated Python wrapper around
them or rewrite historical graph payloads. The individual dispositions follow.

| Location | Disposition |
| --- | --- |
| `docker/codex-acp/LaomedoExtension.test.ts:16` | Retain historical evidence or independent internal test input; no production Python contract. |
| `docker/codex-acp/LaomedoExtension.ts:156` | Retain native JS/TS adapter protocol or rendered view object; language-owned contracts, not Pydantic. |
| `experiments/exp100/native_capture_fixture.mjs:55` | Retain historical evidence or independent internal test input; no production Python contract. |
| `experiments/exp104/active_delivery_fixture.mjs:50` | Retain historical evidence or independent internal test input; no production Python contract. |
| `experiments/exp104/active_delivery_fixture.mjs:57` | Retain historical evidence or independent internal test input; no production Python contract. |
| `experiments/exp89/probe_ui_stop.js:36` | Retain historical evidence or independent internal test input; no production Python contract. |
| `experiments/exp89/probe_ui_stop.js:117` | Retain historical evidence or independent internal test input; no production Python contract. |
| `experiments/exp94/probe_ui_stop.js:36` | Retain historical evidence or independent internal test input; no production Python contract. |
| `experiments/exp94/probe_ui_stop.js:114` | Retain historical evidence or independent internal test input; no production Python contract. |
| `experiments/feasibility/123/probe_agentviz_import.mjs:20` | Retain historical evidence or independent internal test input; no production Python contract. |
| `experiments/feasibility/docker-skill-draft/network-boundary.js:12` | Retain historical evidence or independent internal test input; no production Python contract. |
| `experiments/feasibility/docker-skill-draft/network-boundary.js:42` | Retain historical evidence or independent internal test input; no production Python contract. |
| `frontend/langflow-skill-viewer/AgentActivity.test.tsx:14` | Retain historical evidence or independent internal test input; no production Python contract. |
| `frontend/langflow-skill-viewer/AgentAdvancedControls.test.tsx:6` | Retain historical evidence or independent internal test input; no production Python contract. |
| `frontend/langflow-skill-viewer/AgentAdvancedControls.test.tsx:71` | Retain historical evidence or independent internal test input; no production Python contract. |
| `frontend/langflow-skill-viewer/ClaudeModelDropdown.test.tsx:24` | Retain historical evidence or independent internal test input; no production Python contract. |
| `frontend/langflow-skill-viewer/ClaudeModelDropdown.test.tsx:34` | Retain historical evidence or independent internal test input; no production Python contract. |
| `frontend/langflow-skill-viewer/ClaudeModelDropdown.test.tsx:45` | Retain historical evidence or independent internal test input; no production Python contract. |
| `frontend/langflow-skill-viewer/ClaudeModelDropdown.test.tsx:54` | Retain historical evidence or independent internal test input; no production Python contract. |
| `frontend/langflow-skill-viewer/ClaudeModelDropdown.test.tsx:61` | Retain historical evidence or independent internal test input; no production Python contract. |
| `frontend/langflow-skill-viewer/GraphAgents.test.tsx:12` | Retain historical evidence or independent internal test input; no production Python contract. |
| `frontend/langflow-skill-viewer/GraphAgents.test.tsx:13` | Retain historical evidence or independent internal test input; no production Python contract. |
| `frontend/langflow-skill-viewer/GraphAgents.test.tsx:38` | Retain historical evidence or independent internal test input; no production Python contract. |
| `frontend/langflow-skill-viewer/GraphAgents.test.tsx:39` | Retain historical evidence or independent internal test input; no production Python contract. |
| `frontend/langflow-skill-viewer/GraphAgents.test.tsx:40` | Retain historical evidence or independent internal test input; no production Python contract. |
| `frontend/langflow-skill-viewer/GraphAgents.test.tsx:42` | Retain historical evidence or independent internal test input; no production Python contract. |
| `frontend/langflow-skill-viewer/GraphAgents.test.tsx:55` | Retain historical evidence or independent internal test input; no production Python contract. |
| `frontend/langflow-skill-viewer/GraphAgents.test.tsx:63` | Retain historical evidence or independent internal test input; no production Python contract. |
| `frontend/langflow-skill-viewer/GraphAgents.test.tsx:255` | Retain historical evidence or independent internal test input; no production Python contract. |
| `frontend/langflow-skill-viewer/GraphAgents.test.tsx:259` | Retain historical evidence or independent internal test input; no production Python contract. |
| `frontend/langflow-skill-viewer/GraphAgents.test.tsx:277` | Retain historical evidence or independent internal test input; no production Python contract. |
| `frontend/langflow-skill-viewer/GraphAgents.test.tsx:367` | Retain historical evidence or independent internal test input; no production Python contract. |
| `frontend/langflow-skill-viewer/GraphAgents.test.tsx:391` | Retain historical evidence or independent internal test input; no production Python contract. |
| `frontend/langflow-skill-viewer/GraphAgents.tsx:65` | Retain native JS/TS adapter protocol or rendered view object; language-owned contracts, not Pydantic. |
| `frontend/langflow-skill-viewer/GraphAgents.tsx:223` | Retain native JS/TS adapter protocol or rendered view object; language-owned contracts, not Pydantic. |
| `frontend/langflow-skill-viewer/GraphAgents.tsx:245` | Retain native JS/TS adapter protocol or rendered view object; language-owned contracts, not Pydantic. |
| `frontend/langflow-skill-viewer/GraphAgents.tsx:387` | Retain native JS/TS adapter protocol or rendered view object; language-owned contracts, not Pydantic. |
| `frontend/langflow-skill-viewer/PRViewerModal.test.tsx:20` | Retain historical evidence or independent internal test input; no production Python contract. |
| `frontend/langflow-skill-viewer/PopupFrame.tsx:3` | Retain native JS/TS adapter protocol or rendered view object; language-owned contracts, not Pydantic. |
| `frontend/langflow-skill-viewer/PopupFrame.tsx:7` | Retain native JS/TS adapter protocol or rendered view object; language-owned contracts, not Pydantic. |
| `frontend/langflow-skill-viewer/RunnerRecovery.tsx:135` | Retain native JS/TS adapter protocol or rendered view object; language-owned contracts, not Pydantic. |
| `frontend/langflow-skill-viewer/SkillFileDiff.tsx:50` | Retain native JS/TS adapter protocol or rendered view object; language-owned contracts, not Pydantic. |
| `frontend/langflow-skill-viewer/SkillFileDiff.tsx:77` | Retain native JS/TS adapter protocol or rendered view object; language-owned contracts, not Pydantic. |
| `frontend/langflow-skill-viewer/SkillFileDiff.tsx:80` | Retain native JS/TS adapter protocol or rendered view object; language-owned contracts, not Pydantic. |
| `frontend/langflow-skill-viewer/SkillFilesModal.tsx:68` | Retain native JS/TS adapter protocol or rendered view object; language-owned contracts, not Pydantic. |
| `frontend/langflow-skill-viewer/SkillFilesModal.tsx:70` | Retain native JS/TS adapter protocol or rendered view object; language-owned contracts, not Pydantic. |
| `frontend/langflow-skill-viewer/SkillHistory.test.tsx:6` | Retain historical evidence or independent internal test input; no production Python contract. |
| `frontend/langflow-skill-viewer/SkillHistory.test.tsx:14` | Retain historical evidence or independent internal test input; no production Python contract. |
| `frontend/langflow-skill-viewer/SkillHistory.tsx:88` | Retain native JS/TS adapter protocol or rendered view object; language-owned contracts, not Pydantic. |
| `tests/fixtures/native_command_fixture.mjs:34` | Retain historical evidence or independent internal test input; no production Python contract. |

## Verification limits

Golden payload/hash controls and source-structure checks are internal regression
evidence. They do not certify real provider execution, browser stories or
mailbox mediation. Record installed-candidate and real-flow results separately.
The asynchronous provider dictionaries still own later lifecycle mutations;
this pass does not claim a fully typed mutable run lifecycle.
