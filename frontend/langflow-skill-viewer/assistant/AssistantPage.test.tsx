import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import AssistantPage from "./AssistantPage";
import { assistantRequest, AssistantFailure } from "./api";

jest.mock("./api", () => ({
  ...jest.requireActual("./api"),
  assistantRequest: jest.fn(),
}));
jest.mock("./Message", () => ({
  __esModule: true,
  default: () => null,
  UserMessage: ({ text }: { text: string }) => <p>{text}</p>,
}));
jest.mock("@/icons/OpenAi", () => ({ OpenAiIcon: () => null }));
jest.mock("@/stores/authStore", () => ({
  __esModule: true,
  default: (select: any) => select({ userData: { id: "owner" } }),
}));

describe("uncertain assistant submission", () => {
  it("shows Thinking without retry guidance during dispatch and acknowledged history lag", async () => {
    let acknowledge!: (message: any) => void;
    const acknowledgement = new Promise((resolve) => {
      acknowledge = resolve;
    });
    const conversation = {
      id: "conversation",
      title: "Chat",
      model: "fixture",
      effort: "low",
      state: "idle",
      active_message_id: null,
    };
    let posts = 0;
    let detailReads = 0;
    jest.mocked(assistantRequest).mockImplementation(async (path, body) => {
      if (path === "/models")
        return {
          provider: "codex",
          models: [{ id: "fixture", efforts: ["low"] }],
        };
      if (path === "/conversations")
        return { conversations: [conversation], next_cursor: null };
      if (body) {
        posts += 1;
        return acknowledgement;
      }
      detailReads += 1;
      return { conversation, messages: [], drafts: [], next_cursor: null };
    });
    render(
      <MemoryRouter initialEntries={["/assistant?conversation=conversation"]}>
        <AssistantPage />
      </MemoryRouter>,
    );
    const composer = await screen.findByRole("textbox", {
      name: "Message this assistant",
    });
    await waitFor(() =>
      expect((composer as HTMLTextAreaElement).disabled).toBe(false),
    );
    fireEvent.change(composer, { target: { value: "Hello" } });
    fireEvent.keyDown(composer, { key: "Enter", shiftKey: true });
    fireEvent.keyDown(composer, { key: "Enter", isComposing: true });
    expect(posts).toBe(0);
    expect((composer as HTMLTextAreaElement).value).toBe("Hello");
    fireEvent.keyDown(composer, { key: "Enter" });
    await screen.findByRole("status", { name: "Thinking" });
    expect(
      screen.queryByRole("button", { name: "Retry same submission" }),
    ).toBeNull();
    expect((composer as HTMLTextAreaElement).value).toBe("");
    const beforeAcknowledgement = detailReads;
    acknowledge({ id: "accepted" });
    await waitFor(() =>
      expect(detailReads).toBeGreaterThan(beforeAcknowledgement),
    );
    expect(screen.queryByText(/Reuses its original message ID/)).toBeNull();
    expect(screen.getByRole("status", { name: "Thinking" })).toBeTruthy();
    expect(posts).toBe(1);
  });
  it("renames the conversation explicitly and Escape cancels without a request", async () => {
    const conversation = {
      id: "conversation",
      title: "Original",
      updated_at: 1,
      model: "fixture",
      effort: "low",
      state: "idle",
      active_message_id: null,
    };
    const mutations: unknown[] = [];
    let detailReads = 0;
    jest
      .mocked(assistantRequest)
      .mockImplementation(async (path, body: any, _signal, method) => {
        if (method === "PATCH") {
          mutations.push(body);
          return { ...conversation, title: body.title, updated_at: 2 };
        }
        if (path === "/models")
          return {
            provider: "codex",
            models: [{ id: "fixture", efforts: ["low"] }],
          };
        if (path === "/conversations")
          return { conversations: [conversation], next_cursor: null };
        detailReads += 1;
        return { conversation, messages: [], drafts: [], next_cursor: null };
      });
    render(
      <MemoryRouter initialEntries={["/assistant?conversation=conversation"]}>
        <AssistantPage />
      </MemoryRouter>,
    );
    fireEvent.doubleClick(
      await screen.findByRole("heading", { name: "Original" }),
    );
    fireEvent.change(
      screen.getByRole("textbox", { name: "Conversation title" }),
      { target: { value: "Renamed" } },
    );
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await screen.findByRole("heading", { name: "Renamed" });
    expect(mutations).toEqual([{ title: "Renamed" }]);
    await waitFor(() => expect(detailReads).toBeGreaterThan(1), {
      timeout: 2500,
    });
    expect(screen.getByRole("heading", { name: "Renamed" })).toBeTruthy();
    expect(screen.getByRole("button", { name: /Renamed.*Codex/ })).toBeTruthy();
    fireEvent.doubleClick(screen.getByRole("heading", { name: "Renamed" }));
    fireEvent.keyDown(
      screen.getByRole("textbox", { name: "Conversation title" }),
      { key: "Escape" },
    );
    expect(
      screen.queryByRole("textbox", { name: "Conversation title" }),
    ).toBeNull();
    expect(mutations).toHaveLength(1);
  });
  it("clears retained pending text and its key when the profile locks", async () => {
    sessionStorage.setItem(
      "laomedo.assistant.pending.owner",
      JSON.stringify({
        conversation: {
          id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
          text: "PRIVATE_PENDING_TEXT",
        },
      }),
    );
    jest
      .mocked(assistantRequest)
      .mockRejectedValue(new AssistantFailure("assistant_session_locked"));
    render(
      <MemoryRouter initialEntries={["/assistant?conversation=conversation"]}>
        <AssistantPage />
      </MemoryRouter>,
    );
    await screen.findByRole("heading", { name: "Profile locked" });
    expect(screen.queryByText("PRIVATE_PENDING_TEXT")).toBeNull();
    expect(
      sessionStorage.getItem("laomedo.assistant.pending.owner"),
    ).toBeNull();
  });
  beforeEach(() => {
    sessionStorage.clear();
    jest.clearAllMocks();
  });
  it("retains its key across reload and explicitly retries only that original submission", async () => {
    const messages: any[] = [];
    const posts: any[] = [];
    const conversation = {
      id: "conversation",
      title: "Draft",
      provider: "codex",
      model: "fixture",
      effort: "low",
      state: "idle",
      active_message_id: null,
      error_code: null,
      run_id: null,
      thread_id: null,
      updated_at: 1,
      linked_conversation_id: null,
    };
    jest
      .mocked(assistantRequest)
      .mockImplementation(async (path, body: any) => {
        if (path === "/models")
          return {
            provider: "codex",
            models: [{ id: "fixture", efforts: ["low", "high"] }],
          };
        if (path === "/conversations")
          return { conversations: [conversation], next_cursor: null };
        if (body) {
          posts.push(body);
          if (posts.length === 1)
            throw new AssistantFailure("assistant_dispatch_unknown");
          const message = {
            ...body,
            id: "accepted",
            attempt_id: "attempt",
            native_attempt_id: null,
            state: "completed",
            response: "Done",
            error_code: null,
            run_id: "run",
            created_at: 1,
            stop_requested: false,
          };
          messages.push(message);
          return message;
        }
        return {
          conversation,
          messages: [...messages],
          drafts: [],
          next_cursor: null,
        };
      });
    const mount = () =>
      render(
        <MemoryRouter initialEntries={["/assistant?conversation=conversation"]}>
          <AssistantPage />
        </MemoryRouter>,
      );
    const first = mount();
    const composer = await screen.findByRole("textbox", {
      name: "Message this assistant",
    });
    await waitFor(() =>
      expect((composer as HTMLTextAreaElement).disabled).toBe(false),
    );
    fireEvent.change(composer, {
      target: { value: "Keep this original text" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Choose model and effort" }),
    );
    fireEvent.change(screen.getByRole("slider", { name: "Reasoning effort" }), {
      target: { value: "1" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await screen.findByRole("button", { name: "Retry same submission" });
    const original = JSON.parse(
      sessionStorage.getItem("laomedo.assistant.pending.owner")!,
    );
    expect(original.conversation.id).toBe(posts[0].client_message_id);
    expect(posts[0].model).toBe("fixture");
    expect(posts[0].effort).toBe("high");
    first.unmount();
    mount();
    const retry = await screen.findByRole("button", {
      name: "Retry same submission",
    });
    fireEvent.click(retry);
    await waitFor(() => expect(posts).toHaveLength(2));
    expect(posts[1]).toEqual(posts[0]);
    await waitFor(() =>
      expect(
        screen.queryByRole("button", { name: "Retry same submission" }),
      ).toBeNull(),
    );
  });

  it("starts in a chat composer and creates only on explicit Send, with collapsible history", async () => {
    const calls: any[] = [];
    const conversation = {
      id: "new-chat",
      title: "New conversation",
      model: "fixture",
      effort: "low",
      state: "idle",
      active_message_id: null,
    };
    jest
      .mocked(assistantRequest)
      .mockImplementation(async (path, body: any) => {
        calls.push([path, body]);
        if (path === "/models")
          return {
            provider: "codex",
            models: [{ id: "fixture", efforts: ["low", "high"] }],
          };
        if (path === "/conversations" && body) return conversation;
        if (path === "/conversations")
          return { conversations: [], next_cursor: null };
        return { conversation, messages: [], drafts: [], next_cursor: null };
      });
    render(
      <MemoryRouter initialEntries={["/assistant"]}>
        <AssistantPage />
      </MemoryRouter>,
    );
    const composer = screen.getByRole("textbox", {
      name: "Message this assistant",
    });
    expect(composer.getAttribute("placeholder")).toBe("Start chat…");
    fireEvent.click(
      screen.getByRole("button", { name: "Collapse conversations" }),
    );
    expect(
      screen.queryByRole("complementary", { name: "Conversations" }),
    ).toBeNull();
    fireEvent.click(
      screen.getByRole("button", { name: "Expand conversations" }),
    );
    expect(
      screen.getByRole("button", { name: "New conversation" }),
    ).toBeTruthy();
    await waitFor(() =>
      expect(
        (
          screen.getByRole("button", {
            name: "Choose model and effort",
          }) as HTMLButtonElement
        ).disabled,
      ).toBe(false),
    );
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "Choose model and effort" })
          .textContent,
      ).toContain("fixture"),
    );
    fireEvent.change(composer, { target: { value: "Create a draft" } });
    expect(calls.filter(([, body]) => body)).toHaveLength(0);
    fireEvent.click(screen.getByRole("button", { name: "Start chat" }));
    await waitFor(() =>
      expect(
        calls.some(([path]) => path === "/conversations/new-chat/messages"),
      ).toBe(true),
    );
    expect(
      calls.find(([path]) => path === "/conversations/new-chat/messages")[1],
    ).toMatchObject({
      text: "Create a draft",
      model: "fixture",
      effort: "low",
    });
  });
});
