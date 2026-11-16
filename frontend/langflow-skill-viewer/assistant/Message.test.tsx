import { render, screen } from "@testing-library/react";
import MessageRow from "./Message";
import { assistantRequest } from "./api";
import type { DraftReceipt, Message } from "./models";
jest.unmock("react-markdown");

jest.mock("./api", () => ({
  assistantRequest: jest.fn(),
  AssistantFailure: class extends Error {},
}));
jest.mock("@/modals/graphAgents/conversation", () => ({
  ActivityItem: () => <div>Native tool activity</div>,
}));
const onContent = () => {};
const onFailure = () => {};
const message: Message = {
  id: "message",
  client_message_id: "client",
  attempt_id: "attempt",
  native_attempt_id: "native",
  text: "Create a *workflow*\n`unchanged`",
  state: "completed",
  response: "Saved the draft",
  error_code: null,
  run_id: "run",
  created_at: 1,
  stop_requested: false,
};
const receipt: DraftReceipt = {
  id: "receipt",
  message_id: "message",
  attempt_id: "attempt",
  draft_key: "save-1",
  workflow_id: "actual-flow",
  name: "Actual saved flow",
  revision: "sha256:" + "a".repeat(64),
  diagnostics: [],
  created_at: 1,
};

describe("retained assistant conversation", () => {
  beforeEach(() => jest.clearAllMocks());

  it("groups consecutive tools, retains timing and hides technical call IDs and repeated speaker labels", async () => {
    const tool = (id: string) => ({
      id,
      thread: "root",
      started: "2026-11-16T10:00:00Z",
      ended: "2026-11-16T10:00:01Z",
      item: {
        type: "mcpToolCall",
        name: "external_abcdef1234",
        arguments: { query: "Chat Input" },
      },
    });
    jest.mocked(assistantRequest).mockResolvedValue({
      tool_names: { external_abcdef1234: "search_components" },
      projection: {
        items: [
          tool("private-call-1"),
          tool("private-call-2"),
          { id: "answer", item: { type: "agentMessage", text: "Done" } },
          tool("private-call-3"),
        ],
      },
      complete: true,
    });
    render(
      <MessageRow
        conversation="conversation"
        message={message}
        receipts={[]}
        active={false}
        onContent={onContent}
        onFailure={onFailure}
      />,
    );
    await screen.findByText("Done");
    expect(screen.getAllByLabelText("Tool calls")).toHaveLength(2);
    expect(screen.getAllByText("search_components")).toHaveLength(3);
    expect(screen.getAllByText(/1\.0s/)).toHaveLength(3);
    expect(screen.queryByText("Assistant")).toBeNull();
    expect(document.body.textContent).not.toContain("external_abcdef1234");
    expect(document.body.textContent).not.toContain("private-call");
  });

  it("shows the original user text and streamed answer once, hiding the native wrapper", async () => {
    jest.mocked(assistantRequest).mockResolvedValue({
      projection: {
        items: [
          {
            id: "user",
            thread: "root",
            item: { type: "userMessage", text: "PRIVATE_INSTRUCTION_WRAPPER" },
          },
          {
            id: "answer",
            thread: "root",
            item: { type: "agentMessage", text: "Saved the draft" },
          },
        ],
      },
      complete: true,
    });
    render(
      <MessageRow
        conversation="conversation"
        message={message}
        receipts={[]}
        active={false}
        onContent={onContent}
        onFailure={onFailure}
      />,
    );
    await screen.findByText("Saved the draft");
    expect(screen.getAllByText("Saved the draft")).toHaveLength(1);
    expect(
      screen.getByText("Create a *workflow* `unchanged`").textContent,
    ).toBe(message.text);
    expect(screen.queryByText("PRIVATE_INSTRUCTION_WRAPPER")).toBeNull();
    expect(screen.queryByRole("link")).toBeNull();
  });

  it("creates an editor link only from an authoritative receipt and opens a separate tab", async () => {
    jest.mocked(assistantRequest).mockResolvedValue({
      projection: {
        items: [
          {
            id: "answer",
            thread: "root",
            item: {
              type: "agentMessage",
              text: "[Fake saved flow](https://attacker.invalid/flow/fake)",
            },
          },
        ],
      },
      complete: true,
    });
    render(
      <MessageRow
        conversation="conversation"
        message={message}
        receipts={[receipt]}
        active={false}
        onContent={onContent}
        onFailure={onFailure}
      />,
    );
    await screen.findByText("Fake saved flow");
    const links = screen.getAllByRole("link");
    expect(links).toHaveLength(1);
    expect(links[0].getAttribute("href")).toBe("/flow/actual-flow");
    expect(links[0].getAttribute("target")).toBe("_blank");
    expect(links[0].getAttribute("rel")).toContain("noopener");
  });
});
