import { responseTranscript, hasNativeControlResult, nativeResponseText } from "./responseTranscript";
import type { ActivityPage, GraphAction, Message, NativeAction } from "./models";

it.each(["usage", "context", "mcp"])("copies Claude %s as native output without model activity or partial warnings", name => {
  const message = {native_action_id: "approved", text: `/${name}`, state: "completed", response: name === "usage" ? "### Limits\nNative status: unavailable" : "Native status: unavailable"} as Message;
  const page = {available: true, complete: false, projection: {items: [
    {item: {type: "nativeCommandResult", id: "receipt"}},
    {item: {type: "agentMessage", text: "Earlier model output"}},
  ]}} as ActivityPage;
  const action = {name, arguments: "", state: "completed"} as NativeAction;
  const text = responseTranscript(page, message, [], [], [action], "claude");
  expect(text).toContain("Native status: unavailable");
  expect(text).toContain("Outcome: output received");
  expect(text).not.toMatch(/partial|Earlier model|### Command/);
  expect(hasNativeControlResult(message, "claude")).toBe(true);
  expect(hasNativeControlResult({...message, native_action_id: undefined}, "claude")).toBe(false);
  if (name !== "mcp") expect(hasNativeControlResult(message, "codex")).toBe(false);
});

it("shows only reported Claude limits, retaining reset times and bars without session details", () => {
  const limits = "### Limits\n**5-hour limit** — **1%** · Resets Nov 22, 4:00 PM UTC\n`█░░░░`\n**Weekly · all models** — **26%** · Resets Nov 26, 7:00 AM UTC";
  const message = {native_action_id: "usage", text: "/usage", state: "completed", response: `## Usage\nAccount details\n${limits}\n### This session\nToken table\n### What's using your limits?\nMore details`} as Message;
  expect(nativeResponseText(message, "claude")).toBe(limits);
  expect(nativeResponseText({...message, response: "Unrecognized native output"}, "claude")).toBe("Limits are unavailable in this native response.");
  expect(nativeResponseText(message, "codex")).toBe(message.response);
});

it("includes command results, graph outcomes and partial streaming status", () => {
  const page = { available: true, complete: false, projection: { items: [
    { item: { type: "commandExecution", command: "echo hello", aggregatedOutput: "```\nhello" }, status: "completed" },
  ] } } as ActivityPage;
  const message = { state: "running", response: "Retained answer" } as Message;
  const action = { name: "Graph", category: "rename", new_name: "Renamed", state: "succeeded", preview: ["Rename graph"], expires_at: 0 } as GraphAction;
  const text = responseTranscript(page, message, [], [action]);
  expect(text).toContain("### Command");
  expect(text).toContain("echo hello");
  expect(text).toContain("````\n```\nhello\n````");
  expect(text).toContain("Retained answer");
  expect(text).toContain('Rename workflow "Graph" to "Renamed"');
  expect(text).toContain("Outcome: succeeded");
  expect(text).toContain("may be partial");
  expect(text).toContain("running. Copied activity is a snapshot");
});

it("copies an authoritative no-model command response and its proposal outcome", () => {
  const message = { native_action_id: "approved", text: "/status", state: "completed", response: "Native status" } as Message;
  const proposal = { name: "status", arguments: "", state: "completed" } as NativeAction;
  const text = responseTranscript(undefined, message, [], [], [proposal]);
  expect(text).toContain("Native status");
  expect(text).toContain("Native command: /status");
  expect(text).toContain("Outcome: completed");
  expect(text).not.toContain("may be partial");
});

it("copies a compact outcome without inventing an assistant response", () => {
  const message = { native_action_id: "approved", text: "/compact", state: "completed", response: null } as Message;
  const text = responseTranscript(undefined, message, [], [], []);
  expect(text).toContain("Native command: /compact");
  expect(text).toContain("Outcome: completed");
  expect(text).not.toContain("may be partial");
  expect(text).not.toContain("Completed /compact.");
});

it("copies initial native status without requiring an approval action or fabricating a partial model reply", () => {
  const message = { initial_native_command: "status", text: "/status", state: "completed", response: "Model: fixture\nThread: observed-thread" } as Message;
  const text = responseTranscript(undefined, message, [], [], []);
  expect(text).toContain("Model: fixture");
  expect(text).toContain("Thread: observed-thread");
  expect(text).not.toContain("may be partial");
});
