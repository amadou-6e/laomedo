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
