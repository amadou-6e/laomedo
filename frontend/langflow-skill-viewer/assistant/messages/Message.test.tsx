import { fireEvent, render as renderUI, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import type { ReactElement } from "react";
import MessageRow from "./Message";
import { assistantRequest } from "../api";
import type { DraftReceipt, Message } from "../models";
jest.unmock("react-markdown");
jest.unmock("remark-gfm");
// Message tests exercise shared Markdown, not the separate JSON source viewer.
jest.mock("@/components/core/codeTabsComponent",()=>({__esModule:true,default:({code}:{code:string})=><pre>{code}</pre>}));

jest.mock("../api", () => ({
  assistantRequest: jest.fn(),
  AssistantFailure: class extends Error {},
}));
jest.mock("@/modals/graphAgents/conversation", () => ({
  ActivityItem: () => <div>Native tool activity</div>,
}));
const onContent = () => {};
const render = (element: ReactElement) => renderUI(<MemoryRouter>{element}</MemoryRouter>);
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
  it("shows a retained error once unless its recovery banner already shows it", async () => {
    jest.mocked(assistantRequest).mockResolvedValue({available: true, complete: true, projection: {items: []}});
    const failed = {...message, state: "unknown", error_code: "assistant_cleanup_unverified"};
    const view = render(<MessageRow conversation="conversation" message={failed} receipts={[]} active={false} onContent={onContent} onFailure={onFailure} />);
    expect(screen.getByText(/earlier attempt has not established cleanup/)).toBeVisible();
    view.rerender(<MemoryRouter><MessageRow conversation="conversation" message={failed} receipts={[]} active={false} errorShownAbove onContent={onContent} onFailure={onFailure} /></MemoryRouter>);
    expect(screen.queryByText(/earlier attempt has not established cleanup/)).toBeNull();
    await waitFor(() => expect(screen.getByRole("button", {name: "Copy answer"})).not.toBeDisabled());
  });
  it.each(["usage", "context", "mcp"])("renders Claude %s as native output without a tool row or partial answer", async name => {
    jest.mocked(assistantRequest).mockClear();
    const writeText = jest.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
    const response = name === "usage" ? "### Limits\nNative view output" : "Native view output";
    render(<MessageRow conversation="conversation" provider="claude" message={{...message, text: `/${name}`, native_action_id: "approved", response}} receipts={[]} active={false} onContent={onContent} onFailure={onFailure} />);
    expect(screen.getByLabelText("Native command output")).toHaveTextContent("Native view output");
    expect(screen.getAllByText("Native view output")).toHaveLength(1);
    expect(screen.queryByText("Native tool activity")).toBeNull();
    expect(screen.queryByText(/partial/)).toBeNull();
    expect(assistantRequest).not.toHaveBeenCalled();
    const copy = screen.getByRole("button", { name: "Copy answer" }) as HTMLButtonElement;
    expect(copy.disabled).toBe(false);
    fireEvent.click(copy);
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(response));
  });
  it("waits for retained activity before enabling a response copy", async () => {
    let finish!: (value: unknown) => void;
    jest.mocked(assistantRequest).mockReturnValueOnce(new Promise((resolve) => { finish = resolve; }));
    render(<MessageRow conversation="conversation" message={message} receipts={[]} active={false} onContent={onContent} onFailure={onFailure} />);
    expect((screen.getByRole("button", { name: "Copy answer" }) as HTMLButtonElement).disabled).toBe(true);
    finish({ available: true, complete: true, projection: { items: [] } });
    await waitFor(() => expect((screen.getByRole("button", { name: "Copy answer" }) as HTMLButtonElement).disabled).toBe(false));
  });
  it("copies all agent activity since this request with one response-level control", async () => {
    const writeText = jest.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
    jest.mocked(assistantRequest).mockResolvedValue({ available: true, complete: true,
      tool_names: { external_abcdef: "search_components" },
      projection: { items: [
        { id: "user", item: { type: "userMessage", text: "PRIVATE_WRAPPER" } },
        { id: "first", item: { type: "agentMessage", text: "I will inspect it." } },
        { id: "tool", item: { type: "toolCall", name: "external_abcdef", arguments: { query: "Issue" }, result: { found: 2 }, privateInternal: "HIDDEN_RECORD" } },
        { id: "last", item: { type: "agentMessage", text: "Finished inspecting." } },
      ] },
    });
    render(<MessageRow conversation="conversation" message={message} receipts={[receipt]} active={false} onContent={onContent} onFailure={onFailure} />);
    await screen.findByText("Finished inspecting.");
    expect(screen.getAllByRole("button", { name: "Copy answer" })).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "Copy answer" }));
    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
    const copied = writeText.mock.calls[0][0];
    expect(copied).toContain("I will inspect it.");
    expect(copied).toContain("search_components");
    expect(copied).toContain('"query": "Issue"');
    expect(copied).toContain('"found": 2');
    expect(copied).toContain("Finished inspecting.");
    expect(copied).toContain("Saved draft: Actual saved flow");
    expect(copied.indexOf("I will inspect it.")).toBeLessThan(copied.indexOf("search_components"));
    expect(copied.indexOf("search_components")).toBeLessThan(copied.indexOf("Finished inspecting."));
    expect(copied).not.toMatch(/PRIVATE_WRAPPER|HIDDEN_RECORD|external_abcdef/);
    expect(copied).not.toContain(message.text);
    expect(copied).not.toContain(message.response);
  });
  it("shows accessible Thinking while an admitted response is running", () => {
    jest
      .mocked(assistantRequest)
      .mockResolvedValue({ projection: { items: [] }, complete: true });
    render(
      <MessageRow
        conversation="conversation"
        message={{ ...message, state: "running", response: null }}
        receipts={[]}
        active
        onContent={onContent}
        onFailure={onFailure}
      />,
    );
    expect(screen.getByRole("status", { name: "Thinking" })).toBeTruthy();
    expect(screen.queryByText(/responding/)).toBeNull();
  });
  it.each([true, false])(
    "hides Thinking when an answer is visible (streamed: %s)",
    async (streamed) => {
      jest.mocked(assistantRequest).mockResolvedValue({
        projection: {
          items: streamed
            ? [
                {
                  id: "answer",
                  item: { type: "agentMessage", text: "Answer has started" },
                },
              ]
            : [],
        },
        complete: true,
      });
      render(
        <MessageRow
          conversation="conversation"
          message={{
            ...message,
            state: "running",
            response: streamed ? null : "Answer has started",
          }}
          receipts={[]}
          active
          onContent={onContent}
          onFailure={onFailure}
        />,
      );
      await screen.findByText("Answer has started");
      expect(screen.queryByRole("status", { name: "Thinking" })).toBeNull();
    },
  );
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
