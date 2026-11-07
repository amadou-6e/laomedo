// Internal stream controls. Real browser/refusal/lost-response checks are separate.
import { TextDecoder, TextEncoder } from "util";
import { queryClient } from "@/contexts";
import { BuildStatus } from "@/constants/enums";
import { consumeBackgroundEvents, runFlowAGUI } from "@/controllers/API/agui/run-flow-bridge";
import useFlowStore from "@/stores/flowStore";
import type { VertexBuildTypeAPI } from "@/types/api";
import { processEndVertexEvent } from "@/utils/buildUtils";
import { githubBuildFailure, githubRunFailure } from "./buildOutcome";

beforeAll(() => {
  Object.assign(globalThis, { TextEncoder, TextDecoder });
  if (typeof globalThis.fetch !== "function") globalThis.fetch = jest.fn();
});

beforeEach(() => {
  queryClient.clear();
  useFlowStore.setState({
    nodes: [{ id: "pr", type: "genericNode", position: { x: 0, y: 0 }, data: { id: "pr", type: "LaomedoGitHubPR" } }],
    flowPool: {}, flowBuildStatus: {}, buildInfo: null, isBuilding: true,
  });
});

function entry(status: string, code = "pr_write_unknown"): VertexBuildTypeAPI {
  return {
    id: "pr", run_id: "current-run", valid: true, timestamp: "now",
    inactivated_vertices: null, next_vertices_ids: [], top_level_vertices: [], params: null, artifacts: null, messages: [],
    data: { results: {}, logs: {}, messages: [], outputs: { result: { type: "data", message: {
      schema_version: "laomedo.github-pr.v1", pr: null, operation: { status, error_category: code },
    } } } },
  };
}

function sseResponse(events: object[]): Response {
  const payload = new TextEncoder().encode(events.map(event => `data: ${JSON.stringify(event)}\n\n`).join(""));
  let delivered = false;
  return {
    ok: true, status: 200,
    headers: { get: (key: string) => key.toLowerCase() === "content-type" ? "text/event-stream" : null },
    body: { getReader: () => ({
      read: async () => delivered ? { done: true } : (delivered = true, { done: false, value: payload }),
      cancel: async () => {},
    }) },
    text: async () => "",
  } as unknown as Response;
}

test.each(["failed", "unknown"])("projects %s GitHub output, without treating other components' data as failure", status => {
  expect(githubBuildFailure(entry(status), "LaomedoGitHubPR")?.diagnostics.code).toBe("pr_write_unknown");
  expect(githubBuildFailure(entry(status), "ext:package:LaomedoGitHubPR@1")).toBeDefined();
  expect(githubBuildFailure(entry(status), "TextInput")).toBeUndefined();
  expect(githubBuildFailure(entry("succeeded"), "LaomedoGitHubPR")).toBeUndefined();
  expect(githubBuildFailure(entry("not_requested"), "LaomedoGitHubPR")).toBeUndefined();
});

test("ignores previous-run entries, untouched nodes, and superseded failure output", () => {
  const state = useFlowStore.getState();
  const failure = entry("unknown");
  const snapshot = { nodes: state.nodes, flowPool: { pr: [failure] } };
  expect(githubRunFailure(snapshot, new Set(["pr"]), "other-run")).toBeUndefined();
  expect(githubRunFailure(snapshot, new Set(), "current-run")).toBeUndefined();
  expect(githubRunFailure({ ...snapshot, flowPool: { pr: [failure, entry("succeeded")] } }, new Set(["pr"]), "current-run")).toBeUndefined();
});

test.each(["stream", "background"])("%s completion retains uncertain outcome instead of showing success", async mode => {
  const events = [
    { type: "RUN_STARTED", runId: "current-run", threadId: "thread" },
    { type: "STATE_DELTA", delta: [{ op: "replace", path: "/nodes/pr", value: { status: "success", output: entry("unknown").data } }] },
    { type: "RUN_FINISHED", runId: "current-run", threadId: "thread" },
  ];
  const fetchSpy = jest.spyOn(globalThis, "fetch").mockResolvedValue(sseResponse(events));
  try {
    if (mode === "stream") await runFlowAGUI({ flowId: "flow", message: "check" });
    else await consumeBackgroundEvents("current-run", { flowId: "flow" });
    const state = useFlowStore.getState();
    expect(state.buildInfo).toEqual({ error: ["pr_write_unknown"], success: false });
    expect(state.flowBuildStatus.pr.status).toBe(BuildStatus.ERROR);
    expect(state.flowPool.pr[0].valid).toBe(false);
    expect(state.flowPool.pr[0].data).toEqual(entry("unknown").data);
    expect(state.isBuilding).toBe(false);
  } finally { fetchSpy.mockRestore(); }
});

test("legacy completion reports the domain failure and preserves result data", () => {
  const update = jest.fn(), error = jest.fn(), results: boolean[] = [];
  expect(processEndVertexEvent({ build_data: entry("failed", "pr_grant_unavailable") }, results, { onBuildUpdate: update, onBuildError: error })).toBe(false);
  expect(error).toHaveBeenCalledWith("Error Building Component", ["pr_grant_unavailable"], [{ id: "pr" }]);
  expect(update).toHaveBeenCalledWith(expect.objectContaining({ valid: false, data: entry("failed", "pr_grant_unavailable").data }), BuildStatus.ERROR, "");
  expect(results).toEqual([false]);
});
