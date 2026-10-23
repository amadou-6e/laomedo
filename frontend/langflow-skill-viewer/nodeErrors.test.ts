import { describeNodeFailure, describeLaomedoAlert, hasLaomedoFailure } from "./nodeErrors";
import catalog from "./node-error-catalog.json";

const run = "11111111-1111-4111-8111-111111111111";
const request = "22222222-2222-4222-8222-222222222222";
test.each(Object.keys(catalog))("maps %s without mutating its stable code", code => {
  const failure = describeNodeFailure(code, undefined, { nodeId: "agent", operation: "resume" });
  expect(failure.diagnostics.code).toBe(code);
  expect(failure.title).not.toContain(code);
  expect(failure.description.length).toBeGreaterThan(20);
  expect(failure.recovery.length).toBeGreaterThan(30);
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
