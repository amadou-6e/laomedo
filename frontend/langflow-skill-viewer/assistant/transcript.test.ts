import { conversationTranscript } from "./transcript";
import { assistantRequest } from "./api";
jest.mock("./api", () => ({ assistantRequest: jest.fn() }));

const row = (id: string, created_at: number, response: string | null = null) => ({
  id, created_at, attempt_id: id, text: `Prompt ${id}`, response, state: "completed",
});

it("exports earlier pages once, in order, using displayed answers and excluding tool payloads", async () => {
  const request = jest.mocked(assistantRequest);
  request.mockResolvedValueOnce({ conversation: { title: "My / chat" }, messages: [row("new", 2)], next_cursor: 30 });
  request.mockResolvedValueOnce({ messages: [row("old", 1, "Fallback"), row("new", 2)], next_cursor: null });
  request.mockResolvedValueOnce({ available: true, complete: true, projection: { items: [] } });
  request.mockResolvedValueOnce({ available: true, complete: true, projection: { items: [
    { item: { type: "userMessage", text: "Native wrapper" } },
    { item: { type: "agentMessage", text: "**Actual answer**" } },
    { item: { type: "toolCall", arguments: "Private tool payload" } },
  ] } });
  const result = await conversationTranscript("chat", new AbortController().signal);
  expect(result.filename).toBe("My-chat.md");
  expect(result.text.indexOf("Prompt old")).toBeLessThan(result.text.indexOf("Prompt new"));
  expect(result.text).toContain("Fallback");
  expect(result.text).toContain("**Actual answer**");
  expect(result.text).not.toMatch(/Native wrapper|Private tool payload/);
  expect(result.text.match(/Prompt new/g)).toHaveLength(1);
});

it("states unavailable/partial and active responses instead of claiming complete history", async () => {
  jest.mocked(assistantRequest).mockResolvedValueOnce({ conversation: { title: "Chat" }, messages: [{ ...row("one", 1), state: "running" }], next_cursor: null });
  jest.mocked(assistantRequest).mockResolvedValueOnce({ available: false, complete: false, projection: null });
  const result = await conversationTranscript("chat", new AbortController().signal);
  expect(result.text).toContain("may be partial");
  expect(result.text).toContain("Response state at export: running");
});

it("refuses repeated pagination cursors and propagates read failures without a download", async () => {
  jest.mocked(assistantRequest).mockResolvedValueOnce({ conversation: { title: "Chat" }, messages: [], next_cursor: 0 });
  await expect(conversationTranscript("chat", new AbortController().signal)).rejects.toThrow("Repeated history cursor");
  jest.mocked(assistantRequest).mockRejectedValueOnce(new Error("Read refused"));
  await expect(conversationTranscript("chat", new AbortController().signal)).rejects.toThrow("Read refused");
});
it.each(["usage", "context", "mcp"])("exports Claude %s output without fetching or inventing model activity", async name => {
  jest.mocked(assistantRequest).mockReset();
  jest.mocked(assistantRequest).mockResolvedValueOnce({conversation: {title: "Chat", provider: "claude"}, messages: [{...row("control", 1), native_action_id: "approved", text: `/${name}`, response: "Native view output"}], next_cursor: null});
  const result = await conversationTranscript("chat", new AbortController().signal);
  expect(result.text).toContain("## Native command output\n\nNative view output");
  expect(result.text).not.toMatch(/## Assistant|partial/);
  expect(assistantRequest).toHaveBeenCalledTimes(1);
});
