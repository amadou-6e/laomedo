import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import AssistantPage from "./AssistantPage";
import { assistantRequest, AssistantFailure } from "./api";
import { conversationTranscript, downloadTranscript } from "./transcript";

jest.mock("./transcript", () => ({
  conversationTranscript: jest.fn(),
  downloadTranscript: jest.fn(),
}));

jest.mock("./api", () => ({
  ...jest.requireActual("./api"),
  assistantRequest: jest.fn(),
}));
jest.mock("./Message", () => ({
  __esModule: true,
  default: () => null,
  UserMessage: ({ text }: { text: string }) => <p>{text}</p>,
}));
jest.mock("./assets/openai-logo.svg", () => "openai-logo.svg");
jest.mock("@/components/common/genericIconComponent", () => ({ __esModule: true, default: () => null }));
jest.mock("./assets/opencode-logo-dark.svg", () => "opencode-dark.svg");
jest.mock("./assets/opencode-logo-light.svg", () => "opencode-light.svg");
jest.mock("@/contexts/authContext", () => ({
  AuthContext: jest.requireActual("react").createContext({ userData: { id: "owner" } }),
}));

describe("uncertain assistant submission", () => {
  it("explains an unconnected provider, preserves the draft, then sends through an explicitly selected connected account", async () => {
    const chat = { connection_id: "account", connection_generation: 1, id: "fresh", title: "Hello", provider: "codex", model: "fixture", effort: "low", state: "idle", active_message_id: null };
    jest.mocked(assistantRequest).mockImplementation(async (path, body) => {
      if (path === "/connections") return { connections: [{connection_id: "account", generation: 1, provider: "codex", label: "Saved account", lifecycle: "connected", auth_state: "ready"}] };
      if (path.startsWith("/models?")) return {provider: "codex", models: [{id: "fixture", efforts: ["low"]}]};
      if (path === "/conversations") return body ? chat : {conversations: [], next_cursor: null};
      if (path.endsWith("/messages") && body) return {id: "message", ...body};
      return {conversation: chat, messages: [], drafts: [], next_cursor: null};
    });
    render(<MemoryRouter initialEntries={["/assistant"]}><AssistantPage /></MemoryRouter>);
    const composer = screen.getByRole("textbox", {name: "Message this assistant"});
    fireEvent.change(composer, {target: {value: "Hello"}});
    fireEvent.click(screen.getByRole("radio", {name: "Claude"}));
    await screen.findByText("Connect a Claude account in Settings → Providers to chat.");
    expect(screen.getByRole("button", {name: "Choose model and effort"})).toBeDisabled();
    expect(screen.getByRole("button", {name: "Start chat"})).toBeDisabled();
    expect(screen.getByRole("link", {name: "Connect account ↗"})).toHaveAttribute("href", "/settings/providers");
    expect(composer).toHaveValue("Hello");
    fireEvent.keyDown(composer, {key: "Enter"});
    expect(jest.mocked(assistantRequest).mock.calls.some(([path, body]) => path === "/conversations" && body)).toBe(false);
    expect(jest.mocked(assistantRequest).mock.calls.some(([path]) => path.startsWith("/models?"))).toBe(false);
    fireEvent.click(screen.getByRole("radio", {name: "Codex"}));
    await screen.findByText("Select a Codex account to load its models.");
    fireEvent.click(screen.getByRole("button", {name: "Account"}));
    fireEvent.click(await screen.findByRole("menuitemradio", {name: "Saved account"}));
    await waitFor(() => expect(screen.getByRole("button", {name: "Start chat"})).not.toBeDisabled());
    expect(composer).toHaveValue("Hello");
    fireEvent.keyDown(composer, {key: "Enter"});
    await waitFor(() => expect(assistantRequest).toHaveBeenCalledWith("/conversations/fresh/messages", expect.objectContaining({text: "Hello"})));
  });

  it("sends an incomplete slash prefix as ordinary chat instead of locking the composer", async () => {
    const chat = { connection_id: "account", connection_generation: 1, id: "saved", title: "Saved", provider: "codex", run_id: "run", model: "fixture", effort: "low", state: "idle", active_message_id: null };
    jest.mocked(assistantRequest).mockImplementation(async (path, body) => {
      if (path === "/connections") return {connections: [{connection_id: "account", generation: 1, provider: "codex", label: "Saved account", lifecycle: "connected", auth_state: "ready"}]};
      if (path.startsWith("/models?")) return {provider: "codex", models: [{id: "fixture", efforts: ["low"]}]};
      if (path === "/conversations") return {conversations: [chat], next_cursor: null};
      if (path.endsWith("/native-commands")) return {state: "available", revision: "a".repeat(64), commands: [{name: "status", executable: true, accepts_arguments: false}]};
      if (path.endsWith("/messages") && body) return {id: "message", ...body};
      return {conversation: chat, messages: [], drafts: [], next_cursor: null};
    });
    render(<MemoryRouter initialEntries={["/assistant?conversation=saved"]}><AssistantPage /></MemoryRouter>);
    const composer = screen.getByRole("textbox", {name: "Message this assistant"});
    fireEvent.change(composer, {target: {value: "/sta"}});
    await waitFor(() => expect(screen.getByRole("button", {name: "Send"})).not.toBeDisabled());
    fireEvent.keyDown(composer, {key: "Enter"});
    await waitFor(() => expect(assistantRequest).toHaveBeenCalledWith("/conversations/saved/messages", expect.objectContaining({text: "/sta"})));
    expect(jest.mocked(assistantRequest).mock.calls.some(([path, body]) => path.endsWith("/native-commands") && body)).toBe(false);
  });

  it("recovers from a definite command-input rejection when another command is selected", async () => {
    const chat = { connection_id: "account", connection_generation: 1, id: "saved", title: "Saved", provider: "codex", run_id: "run", model: "fixture", effort: "low", state: "idle", active_message_id: null };
    jest.mocked(assistantRequest).mockImplementation(async (path, body) => {
      if (path === "/connections") return {connections: [{connection_id: "account", generation: 1, provider: "codex", label: "Saved account", lifecycle: "connected", auth_state: "ready"}]};
      if (path.startsWith("/models?")) return {provider: "codex", models: [{id: "fixture", efforts: ["low"]}]};
      if (path === "/conversations") return {conversations: [chat], next_cursor: null};
      if (path.endsWith("/native-commands")) return body ? {id: "action", state: "pending"} : {state: "available", revision: "a".repeat(64), commands: [
        {name: "status", description: "Session status", executable: true, accepts_arguments: false},
        {name: "mcp", description: "MCP tools", executable: true, accepts_arguments: false},
      ]};
      return {conversation: chat, messages: [], drafts: [], next_cursor: null};
    });
    render(<MemoryRouter initialEntries={["/assistant?conversation=saved"]}><AssistantPage /></MemoryRouter>);
    const composer = screen.getByRole("textbox", {name: "Message this assistant"});
    fireEvent.change(composer, {target: {value: "/status extra"}});
    await waitFor(() => expect(screen.getByRole("button", {name: "Send"})).not.toBeDisabled());
    fireEvent.keyDown(composer, {key: "Enter"});
    await waitFor(() => expect(screen.getByRole("button", {name: "Send"})).toBeDisabled());
    fireEvent.change(composer, {target: {value: "/"}});
    fireEvent.click(await screen.findByRole("button", {name: /mcp.*MCP tools/}));
    await waitFor(() => expect(screen.getByRole("button", {name: "Send"})).not.toBeDisabled());
    fireEvent.keyDown(composer, {key: "Enter"});
    await waitFor(() => expect(assistantRequest).toHaveBeenCalledWith("/conversations/saved/native-commands", expect.objectContaining({name: "mcp", arguments: ""})));
    expect(jest.mocked(assistantRequest).mock.calls.some(([path]) => path.endsWith("/messages"))).toBe(false);
  });

  it("starts a brand-new Codex chat with explicit native status rather than a hidden prompt", async () => {
    const chat = { connection_id: "account", connection_generation: 1, id: "fresh", title: "/status", provider: "codex", run_id: null, model: "fixture", effort: "low", state: "idle", active_message_id: null };
    jest.mocked(assistantRequest).mockImplementation(async (path, body) => {
      if (path === "/connections") return { connections: [{connection_id: "account", generation: 1, provider: "codex", label: "Saved account", lifecycle: "connected", auth_state: "ready"}] };
      if (path.startsWith("/models?")) return {provider: "codex", models: [{id: "fixture", efforts: ["low"]}]};
      if (path === "/conversations") return body ? chat : {conversations: [], next_cursor: null};
      if (path.endsWith("/messages") && body) return {id: "initial-status", ...body};
      return {conversation: chat, messages: [], drafts: [], next_cursor: null};
    });
    render(<MemoryRouter initialEntries={["/assistant"]}><AssistantPage /></MemoryRouter>);
    fireEvent.click(await screen.findByRole("button", {name: "Account"}));
    fireEvent.click(await screen.findByRole("menuitemradio", {name: "Saved account"}));
    const composer = screen.getByRole("textbox", {name: "Message this assistant"});
    fireEvent.change(composer, {target: {value: "/status "}});
    await waitFor(() => expect(screen.getByRole("button", {name: "Start chat"})).not.toBeDisabled());
    fireEvent.click(screen.getByRole("button", {name: "Start chat"}));
    await waitFor(() => expect(assistantRequest).toHaveBeenCalledWith("/conversations/fresh/messages", expect.objectContaining({text: "/status", initial_native_command: "status"})));
    expect(jest.mocked(assistantRequest).mock.calls.some(([path]) => path.endsWith("/native-commands"))).toBe(false);
  });
  it("submits a typed command directly and never wraps it in a model message", async () => {
    const chat = { connection_id: "account", connection_generation: 1, id: "saved", title: "Saved", provider: "codex", run_id: "run", model: "fixture", effort: "low", state: "idle", active_message_id: null };
    jest.mocked(assistantRequest).mockImplementation(async (path, body) => {
      if (path === "/connections") return { connections: [{connection_id: "account", generation: 1, provider: "codex", label: "Saved account", lifecycle: "connected", auth_state: "ready"}] };
      if (path.startsWith("/models?")) return { provider: "codex", models: [{id: "fixture", efforts: ["low"]}] };
      if (path === "/conversations") return {conversations: [chat], next_cursor: null};
      if (path.endsWith("/native-commands")) return body ? {id: "action", state: "executing"} : {state: "available", revision: "a".repeat(64), commands: [{name: "status", executable: true, accepts_arguments: false, description: "Session status"}]};
      return {conversation: chat, messages: [], drafts: [], next_cursor: null};
    });
    render(<MemoryRouter initialEntries={["/assistant?conversation=saved"]}><AssistantPage /></MemoryRouter>);
    const composer = screen.getByRole("textbox", {name: "Message this assistant"});
    fireEvent.change(composer, {target: {value: "/status"}});
    await waitFor(() => expect(screen.getByRole("button", {name: "Send"})).not.toBeDisabled());
    fireEvent.keyDown(composer, {key: "Enter"});
    await waitFor(() => expect(assistantRequest).toHaveBeenCalledWith("/conversations/saved/native-commands", expect.objectContaining({name: "status", arguments: "", catalog_revision: "a".repeat(64)})));
    await waitFor(() => expect(composer).toHaveValue(""));
    expect(jest.mocked(assistantRequest).mock.calls.some(([path]) => path.endsWith("/messages"))).toBe(false);
  });
  it("lets a user draft immediately while the selected provider's model discovery is pending", async () => {
    const chat = { connection_id: "account", connection_generation: 1, id: "saved", title: "Saved", provider: "codex", model: "fixture", effort: "low", state: "idle", active_message_id: null };
    let finish!: (value: unknown) => void;
    jest.mocked(assistantRequest).mockImplementation(async path => {
      if (path === "/connections") return { connections: [{connection_id: "account", generation: 1, provider: "codex", label: "Saved account", lifecycle: "connected", auth_state: "ready"}] };
      if (path.startsWith("/models?")) return new Promise(resolve => { finish = resolve; });
      if (path === "/conversations") return { conversations: [chat], next_cursor: null };
      return { conversation: chat, messages: [], drafts: [], next_cursor: null };
    });
    render(<MemoryRouter initialEntries={["/assistant?conversation=saved"]}><AssistantPage /></MemoryRouter>);
    const composer = await screen.findByRole("textbox", { name: "Message this assistant" });
    await waitFor(() => expect(finish).toBeDefined());
    expect(composer).not.toHaveAttribute("readonly");
    fireEvent.change(composer, { target: { value: "My next question" } });
    expect(composer).toHaveValue("My next question");
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
    await act(async () => finish({ provider: "codex", models: [{ id: "fixture", efforts: ["low"] }] }));
    expect(composer).toHaveValue("My next question");
  });
  it("puts conversation title and full-window action in one header and keeps the action reachable in history", async()=>{
    const chat={id:"saved",title:"Hello",model:"fixture",effort:"low",state:"idle",active_message_id:null};
    jest.mocked(assistantRequest).mockImplementation(async path=>{
      if (path === "/connections") return { connections: [{connection_id: "account", generation: 1, provider: "codex", label: "Saved account", lifecycle: "connected", auth_state: "ready"}] };
      if(path.startsWith("/models?"))return {provider:"codex",models:[{id:"fixture",efforts:["low"]}]};
      if(path==="/conversations")return {conversations:[chat],next_cursor:null};
      return {conversation:chat,messages:[],drafts:[],next_cursor:null};
    });
    render(<MemoryRouter><AssistantPage embedded selectedConversation="saved" headerActions={<a href="/assistant">Full-window chat</a>}/></MemoryRouter>);
    const title=await screen.findByRole("heading",{name:"Hello"});
    expect(title.closest("header")).toContainElement(screen.getByRole("link",{name:"Full-window chat"}));
    fireEvent.click(screen.getByRole("button",{name:"Expand conversations"}));
    expect(screen.getByRole("link",{name:"Full-window chat"})).toBeVisible();
    expect(screen.getByRole("heading",{name:"Conversations"})).toBeVisible();
  });
  it("selects saved sidebar conversations without replacing the graph URL", async () => {
    const first = { connection_id: "account", connection_generation: 1, id: "first", title: "First saved chat", provider: "codex", model: "fixture", effort: "low", state: "idle", active_message_id: null };
    const second = { connection_id: "account", connection_generation: 1, ...first, id: "second", title: "Second saved chat" };
    jest.mocked(assistantRequest).mockImplementation(async (path) => {
      if (path === "/connections") return { connections: [{connection_id: "account", generation: 1, provider: "codex", label: "Saved account", lifecycle: "connected", auth_state: "ready"}] };
      if (path.startsWith("/models?")) return { provider: "codex", models: [{ id: "fixture", efforts: ["low"] }] };
      if (path === "/conversations") return { conversations: [first, second], next_cursor: null };
      return { conversation: path.includes("second") ? second : first, messages: [], drafts: [], next_cursor: null };
    });
    const select = jest.fn();
    render(<MemoryRouter initialEntries={["/flow/graph?canvas=preserved"]}><AssistantPage embedded selectedConversation="first" onSelectConversation={select} /></MemoryRouter>);
    fireEvent.click(await screen.findByRole("button", { name: "Expand conversations" }));
    fireEvent.click(await screen.findByRole("button", { name: /^Second saved chat/ }));
    expect(select).toHaveBeenCalledWith({ conversation: "second" });
    expect(screen.getByRole("button", { name: "Expand conversations" })).toBeInTheDocument();
    expect(jest.mocked(assistantRequest).mock.calls.every(([, body]) => body === undefined)).toBe(true);
  });
  it("abandons an in-flight export when the conversation changes", async () => {
    let finish!: (value: { text: string; filename: string }) => void;
    jest.mocked(conversationTranscript).mockReturnValueOnce(new Promise((resolve) => { finish = resolve; }));
    const first = { connection_id: "account", connection_generation: 1, id: "first", title: "First", provider: "codex", model: "fixture", effort: "low", state: "idle", active_message_id: null };
    const second = { connection_id: "account", connection_generation: 1, ...first, id: "second", title: "Second" };
    jest.mocked(assistantRequest).mockImplementation(async (path) => {
      if (path === "/connections") return { connections: [{connection_id: "account", generation: 1, provider: "codex", label: "Saved account", lifecycle: "connected", auth_state: "ready"}] };
      if (path.startsWith("/models?")) return { provider: "codex", models: [{ id: "fixture", efforts: ["low"] }] };
      if (path === "/conversations") return { conversations: [first, second], next_cursor: null };
      return { conversation: path.includes("second") ? second : first, messages: [], drafts: [], next_cursor: null };
    });
    render(<MemoryRouter initialEntries={["/assistant?conversation=first"]}><AssistantPage /></MemoryRouter>);
    fireEvent.click(await screen.findByRole("button", { name: "Export conversation" }));
    const signal = jest.mocked(conversationTranscript).mock.calls[0][1];
    fireEvent.click(screen.getByRole("button", { name: /^Second/ }));
    await waitFor(() => expect(signal.aborted).toBe(true));
    finish({ text: "Private old conversation", filename: "old.md" });
    await waitFor(() => expect(screen.queryByText("Exporting...")).toBeNull());
    expect(downloadTranscript).not.toHaveBeenCalled();
  });
  it("shows Thinking without retry guidance during dispatch and acknowledged history lag", async () => {
    let acknowledge!: (message: any) => void;
    const acknowledgement = new Promise((resolve) => {
      acknowledge = resolve;
    });
    const conversation = { connection_id: "account", connection_generation: 1,
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
      if (path === "/connections") return { connections: [{connection_id: "account", generation: 1, provider: "codex", label: "Saved account", lifecycle: "connected", auth_state: "ready"}] };
      if (path.startsWith("/models?"))
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
    composer.focus();
    fireEvent.keyDown(composer, { key: "Enter" });
    await screen.findByRole("status", { name: "Thinking" });
    expect(document.activeElement).toBe(composer);
    expect((composer as HTMLTextAreaElement).readOnly).toBe(true);
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
  it("does not send a retained draft with Enter after attention arrives", async () => {
    let state = "idle";
    let posts = 0;
    const conversation = () => ({
      id: "conversation",
      title: "Chat",
      model: "fixture",
      effort: "low",
      state,
      active_message_id: null,
    });
    jest.mocked(assistantRequest).mockImplementation(async (path, body) => {
      if (path === "/connections") return { connections: [{connection_id: "account", generation: 1, provider: "codex", label: "Saved account", lifecycle: "connected", auth_state: "ready"}] };
      if (path.startsWith("/models?"))
        return {
          provider: "codex",
          models: [{ id: "fixture", efforts: ["low"] }],
        };
      if (body) {
        posts += 1;
        return {};
      }
      if (path === "/conversations")
        return { conversations: [conversation()], next_cursor: null };
      return {
        conversation: conversation(),
        messages: [],
        drafts: [],
        next_cursor: null,
      };
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
      expect((composer as HTMLTextAreaElement).readOnly).toBe(false),
    );
    fireEvent.change(composer, { target: { value: "Keep this draft" } });
    state = "attention";
    await waitFor(
      () => expect((composer as HTMLTextAreaElement).readOnly).toBe(true),
      { timeout: 3000 },
    );
    composer.focus();
    fireEvent.keyDown(composer, { key: "Enter" });
    expect(posts).toBe(0);
    expect((composer as HTMLTextAreaElement).value).toBe("Keep this draft");
    expect(document.activeElement).toBe(composer);
  });
  it("renames the conversation explicitly and Escape cancels without a request", async () => {
    const conversation = { connection_id: "account", connection_generation: 1,
      id: "conversation",
      title: "Original",
      provider: "codex",
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
        if (path === "/connections") return {connections: [{connection_id: "account", generation: 1, provider: "codex", label: "Saved account", lifecycle: "connected", auth_state: "ready"}, {connection_id: "claude-account", generation: 1, provider: "claude", label: "Claude account", lifecycle: "connected", auth_state: "ready"}]};
        if (method === "PATCH") {
          mutations.push(body);
          return { ...conversation, title: body.title, updated_at: 2 };
        }
        if (path.startsWith("/models?"))
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
    const conversation = { connection_id: "account", connection_generation: 1,
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
        if (path === "/connections") return {connections: [{connection_id: "account", generation: 1, provider: "codex", label: "Saved account", lifecycle: "connected", auth_state: "ready"}, {connection_id: "claude-account", generation: 1, provider: "claude", label: "Claude account", lifecycle: "connected", auth_state: "ready"}]};
        if (path.startsWith("/models?"))
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
    const conversation = { connection_id: "account", connection_generation: 1,
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
        if (path === "/connections") return {connections: [{connection_id: "account", generation: 1, provider: "codex", label: "Saved account", lifecycle: "connected", auth_state: "ready"}, {connection_id: "claude-account", generation: 1, provider: "claude", label: "Claude account", lifecycle: "connected", auth_state: "ready"}]};
        calls.push([path, body]);
        if (path.startsWith("/models?"))
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
    fireEvent.click(await screen.findByRole("button", {name: "Account"}));
    fireEvent.click(await screen.findByRole("menuitemradio", {name: "Saved account"}));
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
  it("does not replace selected-account models with a late discovery from another account", async () => {
    let finish!: (value: unknown) => void;
    const codex = new Promise(resolve => { finish = resolve; });
    jest.mocked(assistantRequest).mockImplementation(async path => {
      if (path === "/connections") return { connections: [
        {connection_id: "account", generation: 1, provider: "codex", label: "Saved account", lifecycle: "connected", auth_state: "ready"},
        {connection_id: "claude-account", generation: 2, provider: "claude", label: "Claude account", lifecycle: "connected", auth_state: "ready"},
      ] };
      if (path.startsWith("/models?provider=claude")) return {provider: "claude", models: [{id: "claude-fixture", efforts: ["default"]}]};
      if (path.startsWith("/models?")) return codex;
      return {conversations: [], next_cursor: null};
    });
    render(<MemoryRouter><AssistantPage /></MemoryRouter>);
    await waitFor(() => expect(assistantRequest).toHaveBeenCalledWith("/connections"));
    expect(jest.mocked(assistantRequest).mock.calls.some(([path]) => path.startsWith("/models"))).toBe(false);
    fireEvent.click(screen.getByRole("button", {name: "Account"}));
    fireEvent.click(await screen.findByRole("menuitemradio", {name: "Saved account"}));
    await waitFor(() => expect(assistantRequest).toHaveBeenCalledWith(expect.stringContaining("provider=codex")));
    fireEvent.click(screen.getByRole("radio", {name: "Claude"}));
    fireEvent.click(screen.getByRole("button", {name: "Account"}));
    fireEvent.click(await screen.findByRole("menuitemradio", {name: "Claude account"}));
    await waitFor(() => expect(screen.getByRole("button", {name: "Choose model and effort"})).toHaveTextContent("claude-fixture"));
    await act(async () => { finish({provider: "codex", models: [{id: "wrong-provider", efforts: ["low"]}]}); await codex; });
    expect(screen.getByRole("button", {name: "Choose model and effort"})).toHaveTextContent("claude-fixture");
    expect(screen.getByRole("radio", {name: "Claude"})).toBeChecked();
  });
});
