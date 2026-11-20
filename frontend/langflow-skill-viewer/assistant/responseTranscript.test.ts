import { responseTranscript } from "./responseTranscript";
import type { ActivityPage, GraphAction, Message } from "./models";

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
