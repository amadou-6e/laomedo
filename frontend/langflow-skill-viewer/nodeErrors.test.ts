import { describeNodeFailure, describeLaomedoAlert, hasLaomedoFailure, isKnownNodeError } from "./nodeErrors";
import catalog from "./node-error-catalog.json";

test("native request timeout keeps its safe method code and descriptive recovery", () => {
 const code="request_timeout:model/list";
 const failure=describeNodeFailure(`Laomedo run 11111111-1111-4111-8111-111111111111 failed: ${code}`,undefined,{nodeId:"agent"});
 expect(failure.title).toBe("The Agent did not respond in time");
 expect(failure.diagnostics.code).toBe(code);
 expect(failure.recovery).toContain("If a run started");
 expect(failure.recovery).toContain("metadata-only");
 expect(isKnownNodeError(code,true)).toBe(true);
});

test("native timeout parsing rejects arbitrary method payloads", () => {
 const failure=describeNodeFailure("request_timeout:https://private-token.example/secret",undefined,{nodeId:"agent"});
 expect(failure.title).toBe("The node could not confirm completion");
 expect(JSON.stringify(failure)).not.toContain("private-token");
});

test.each(["new", "load", "set_config_option", "cancel"])("ACP %s timeout preserves its code and existing descriptive recovery", method => {
 const code=`request_timeout:session/${method}`;
 const failure=describeNodeFailure(code,undefined,{nodeId:"agent"});
 expect(failure.title).toBe("The Agent did not respond in time");
 expect(failure.diagnostics.code).toBe(code);
 expect(failure.recovery).toContain("If a run started");
});

test("ACP timeout method allowlist excludes execution tunnels and payload suffixes", () => {
 for (const code of ["request_timeout:session/exec", "request_timeout:session/new?secret=private"]) {
  const failure=describeNodeFailure(code,undefined,{nodeId:"agent"});
  expect(failure.title).toBe("The node could not confirm completion");
  expect(JSON.stringify(failure)).not.toContain("private");
 }
});

const run = "11111111-1111-4111-8111-111111111111";
const request = "22222222-2222-4222-8222-222222222222";
test("Claude model failures retain their code and redact native payload details",()=>{
 const failure=describeNodeFailure('Error building Component LaomedoClaudeAgent: \n\nunsupported_claude_effort; private-native-payload',undefined,
  {nodeId:'agent',nodeType:'LaomedoClaudeAgent',operation:'fresh'});
 expect(failure.title).toBe('This Claude model does not support that effort');
 expect(failure.recovery).toContain('Reasoning Effort');
 expect(failure.diagnostics.code).toBe('unsupported_claude_effort');
 expect(JSON.stringify(failure)).not.toContain('private-native-payload');
 const unknown=describeNodeFailure('claude_future_failure_2',undefined,{nodeType:'LaomedoClaudeAgent'});
 expect(unknown.diagnostics.code).toBe('claude_future_failure_2');
 expect(unknown.description).toContain('cause has not been established');
 expect(unknown.recovery).toContain('before starting another request');
});
test("a model-refresh alert attaches actionable recovery for its real error-details control",()=>{
 const value=describeLaomedoAlert({title:'Refresh failed',list:['runner_model_catalog_unavailable_check_runner_connection']},true);
 expect(value.title).toBe('The model list could not be loaded');
 expect(value.failure?.recovery).toContain('open Model and use Refresh');
 expect(value.list?.join(' ')).toContain('Open Error details');
 expect(value.list?.join(' ')).not.toContain(value.failure?.recovery);
 expect(value.diagnosticCode).toBe('runner_model_catalog_unavailable_check_runner_connection');
});
test.each(Object.keys(catalog))("maps %s without mutating its stable code", code => {
  const failure = describeNodeFailure(code, undefined, { nodeId: "agent", operation: "resume" });
  expect(failure.diagnostics.code).toBe(code);
  expect(failure.title).not.toContain(code);
  expect(failure.description.length).toBeGreaterThan(20);
  // Startup failure is informational: no unconfirmed fix or separate operator.
  if (code === "runner_start_cancelled") {
    expect(failure.recovery).toBe("");
  } else if (code === "runner_start_failed") {
    expect(failure.description).toBe("The local runner exited before it was ready.");
    expect(failure.recovery).toBe("");
  } else expect(failure.recovery.length).toBeGreaterThan(30);
});

test("missing reference advice only mentions controls actually available", () => {
  const value = describeNodeFailure("prior_run_required", undefined, { operation: "resume" });
  expect(value.title).toBe("No previous run is available");
  expect(value.recovery).toContain("saved flow or API request");
  expect(value.recovery).not.toContain("Select one");
});

test("saved reference presence is distinguished without inventing a loading cause", () => {
  const value = describeNodeFailure("prior_run_required", undefined, { savedReferences: ["", JSON.stringify({ run_id: run })] });
  expect(value.title).toBe("The saved run reference was not accepted");
  expect(value.description).toContain("reason has not been established");
  expect(value.diagnostics.code).toBe("prior_run_required");
  expect(value.diagnostics.reference_state).toBe("saved_reference_present");
  expect(describeNodeFailure("prior_run_required", undefined, { savedReferences: ["{bad"] }).title).toBe("The previous run reference could not be read");
});

test("native exception wrapping and safe identifiers survive presentation", () => {
  const value = describeNodeFailure(`Error building Component LaomedoCodexAgent: \n\nLaomedo run ${run} failed: unsupported_model_effort`, { run_id: request }, { nodeId: "Agent-original", operation: "fresh" });
  expect(value.diagnostics).toEqual({ code: "unsupported_model_effort", node_id: "Agent-original", operation: "fresh", graph_execution_id: request, run_id: run });
});

test("a structured failed runner result is explained even when graph routing succeeded", () => {
  const reference = Object.freeze({ status: "failed", error_category: "model_turn_cap_reached", run_id: run, request_id: request });
  const status = { data: { outputs: { outcome: { message: { run_reference: reference } } } } };
  expect(hasLaomedoFailure(status)).toBe(true);
  expect(describeNodeFailure("", status).diagnostics).toEqual({ code: "model_turn_cap_reached", run_id: run, request_id: request });
  expect(reference.error_category).toBe("model_turn_cap_reached");
  expect(hasLaomedoFailure({ data: { outputs: { result: { message: { status: "completed", error_category: null, run_id: run } } } } })).toBe(false);
});

test("unknown errors are useful without exposing raw exception data", () => {
  const future = describeNodeFailure("future_runtime_condition", undefined);
  expect(future.diagnostics.code).toBe("future_runtime_condition");
  expect(future.description).toContain("cause has not been established");
  const secret = "Bearer sk-private-value https://example.test/?token=private";
  const value = describeNodeFailure(secret, { params: secret, data: { outputs: { run: { message: { status: "unknown", error_category: "runner_transport_failed", run_id: secret, authorization: secret, stackTrace: secret } } } } });
  expect(JSON.stringify(value)).not.toContain("private");
  expect(value.diagnostics).toEqual({ code: "runner_transport_failed" });
  expect(describeNodeFailure("my_secret_password", undefined).diagnostics.code).toBe("unrecognized_error");
});

test.each(["runner_transport_failed", "runner_status_unknown", "runner_wait_deadline", "future_condition"])("%s never recommends an unsafe retry", code => {
  const value = describeNodeFailure(code, undefined);
  expect(value.recovery).toMatch(/before starting another|before starting new/);
  expect(value.recovery).not.toMatch(/try again|retry|press Run/i);
});

test("start response loss preserves its request identity without repeating dispatch", () => {
  const failure = describeNodeFailure(`runner_transport_failed; start outcome unknown; check status for request_id before starting again: ${request}`, undefined);
  expect(failure.diagnostics.request_id).toBe(request);
});

test("known codes and branded Laomedo toasts are explained; API objects stay untouched", () => {
  const original = Object.freeze({ title: "Last build failed", list: ["Error building Component LaomedoCodexAgent: \n\nprior_run_required"] });
  expect(describeLaomedoAlert(original).title).toBe("No previous run is available");
  expect(original.list[0]).toContain("prior_run_required");
  expect(describeLaomedoAlert({ title: "Workflow run failed", list: ["prior_run_required"] }, true).title).toBe("No previous run is available");
  const other = { title: "Other application error", list: ["Unrelated failure"] };
  expect(describeLaomedoAlert(other)).toBe(other);
});

test("unknown codes with numeric segments remain available without a claimed cause", () => {
 expect(describeNodeFailure("future_error_240", undefined).diagnostics.code).toBe("future_error_240");
 expect(describeNodeFailure("timeout_must_be_1_to_240_seconds", undefined).title).toBe("The HTTP timeout is outside its allowed range");
 const other = {title:"Other application",list:["unauthorized"]};
 expect(describeLaomedoAlert(other)).toBe(other);
});

test("notification diagnostics come from the matched failure rather than the first item", () => {
 const value = describeLaomedoAlert({title:"Failure",list:["Unrelated context", "prior_run_required"]}, true);
 expect(value.diagnosticCode).toBe("prior_run_required");
 expect(value.list).toHaveLength(2);
});

test("future safe codes and branded unknown failures use the descriptive flow path", () => {
 expect(isKnownNodeError("future_condition_240", true)).toBe(false);
 expect(isKnownNodeError("Error building Component Laomedo Codex Agent: \n\nUnrecognized provider response")).toBe(true);
 expect(isKnownNodeError("An unrelated ordinary message")).toBe(false);
 expect(isKnownNodeError("future_condition_240")).toBe(false);
 expect(isKnownNodeError("unauthorized")).toBe(false);
});

test("a mixed graph leaves another component's snake case alert intact", () => {
 const other = { title: "Other component failed", list: ["future_condition_240"] };
 expect(describeLaomedoAlert(other, true)).toBe(other);
 expect(describeLaomedoAlert({ title: "Failure", list: ["Error building Component LaomedoClaudeAgent: \n\nfuture_condition_240"] }, true).diagnosticCode).toBe("future_condition_240");
});

test('invalid connected skills describe the optional zero-skill path without losing diagnostics',()=>{
 const failure=describeNodeFailure('invalid_skill_reference',undefined);
 expect(failure.description).toContain('Skills are optional');
 expect(failure.recovery).toContain('disconnect Skill References');
 expect(failure.diagnostics.code).toBe('invalid_skill_reference');
 expect(JSON.stringify(describeNodeFailure('Bearer sk-private-value',undefined))).not.toContain('private-value');
 expect(describeNodeFailure('one_to_sixteen_skills_required',undefined).description).toContain('more than sixteen');
});

test('saved graph authentication failures preserve their code and redact private details',()=>{
 const failure=describeNodeFailure('saved_flow_fetch_failed; Bearer sk-private-value',undefined);
 expect(failure.diagnostics.code).toBe('saved_flow_fetch_failed');
 expect(failure.title).toContain('saved graph');
 expect(failure.recovery).toContain('Langflow');
 expect(JSON.stringify(failure)).not.toContain('private-value');
 expect(describeNodeFailure('unfamiliar_saved_flow_failure',undefined).diagnostics.code).toBe('unfamiliar_saved_flow_failure');
});

test('invalid handoff selections explain the actual parameter without exposing its contents',()=>{
 const failure=describeNodeFailure('invalid_handoff_artifact_selection; Bearer sk-private-value',undefined);
 expect(failure.diagnostics.code).toBe('invalid_handoff_artifact_selection');
 expect(failure.recovery).toContain('Selected Artifact References');
 expect(JSON.stringify(failure)).not.toContain('private-value');
});

test("legacy Agent inheritance reports migration without leaking payloads or suggesting a blind retry", () => {
 const failure = describeNodeFailure("Error building Component LaomedoClaudeAgent: \n\nagent_component_migration_required; private-native-payload", undefined,
   {nodeId: "agent", nodeType: "LaomedoClaudeAgent", operation: "fresh"});
 expect(failure.title).toBe("This saved Agent node needs an update");
 expect(failure.description).toContain("stopped before sending a request");
 expect(failure.recovery).toContain("migrate a copy");
 expect(failure.diagnostics.code).toBe("agent_component_migration_required");
 expect(JSON.stringify(failure)).not.toContain("private-native-payload");
 expect(failure.recovery).not.toMatch(/retry|operator|restart/i);
});

test.each(["sk_", "ghp_", "gho_", "ghu_", "ghs_", "ghr_", "github_pat_"]
 .flatMap(prefix => [prefix + "a".repeat(36), prefix.toUpperCase() + "A".repeat(36)]))(
 "credential-shaped unknown code is redacted from shared diagnostics: %s", code => {
  for (const failure of [describeNodeFailure(code, undefined), describeNodeFailure(undefined,
   {data: {outputs: {run: {message: {status: "failed", error_category: code}}}}})]) {
   expect(failure.diagnostics.code).toBe("unrecognized_error");
   expect(JSON.stringify(failure)).not.toContain(code);
  }
 });

test("credential-prefix filtering preserves admitted catalogue, native timeout and safe unknown codes", () => {
 expect(describeNodeFailure("skill_operation_invalid", undefined).diagnostics.code).toBe("skill_operation_invalid");
 expect(describeNodeFailure("request_timeout:session/new", undefined).diagnostics.code).toBe("request_timeout:session/new");
 expect(describeNodeFailure("future_inspection_condition", undefined).diagnostics.code).toBe("future_inspection_condition");
});

test.each(["sk_", "ghp_", "gho_", "ghu_", "ghs_", "ghr_", "github_pat_"]
 .flatMap(prefix => [prefix + "a".repeat(36), prefix.toUpperCase() + "A".repeat(36)]))(
 "credential-shaped node identifiers are redacted from shared diagnostics: %s", nodeId => {
  const failure = describeNodeFailure("skill_operation_invalid", undefined, { nodeId });
  expect(failure.diagnostics.code).toBe("skill_operation_invalid");
  expect(failure.diagnostics.node_id).toBeUndefined();
  expect(JSON.stringify(failure)).not.toContain(nodeId);
 });


test.each(["sk_", "sk-", "sk-proj-", "ghp_", "gho_", "ghu_", "ghs_", "ghr_", "github_pat_"]
 .flatMap(prefix => ["wrapped_" + prefix + "a".repeat(36), "node-" + prefix.toUpperCase() + "A".repeat(36), "foo" + prefix + "a".repeat(36)]))(
 "embedded credential markers are absent from raw/structured/node diagnostics: %s", value => {
  const raw=describeNodeFailure(value,undefined);
  const structured=describeNodeFailure(undefined,{data:{outputs:{run:{message:{status:"failed",error_category:value}}}}});
  const node=describeNodeFailure("skill_operation_invalid",undefined,{nodeId:value});
  expect(raw.diagnostics.code).toBe("unrecognized_error");expect(structured.diagnostics.code).toBe("unrecognized_error");
  expect(node.diagnostics.code).toBe("skill_operation_invalid");expect(node.diagnostics.node_id).toBeUndefined();
  for(const failure of [raw,structured,node])expect(JSON.stringify(failure)).not.toContain(value);
 });

test.each(["task_failed", "mask_unavailable", "future_error_240", "agent_task_1"])("ordinary word endings remain safe unknown codes: %s", code=>{
 expect(describeNodeFailure(code,undefined).diagnostics.code).toBe(code);
});

test.each(["ghp_", "SK-", "github_pat_"])("short embedded markers at segment boundaries are excluded without a payload-length guess: %s", marker=>{
 expect(describeNodeFailure("wrapped_"+marker+"x",undefined).diagnostics.code).toBe("unrecognized_error");
 expect(describeNodeFailure("skill_operation_invalid",undefined,{nodeId:"node-"+marker+"x"}).diagnostics.node_id).toBeUndefined();
});
