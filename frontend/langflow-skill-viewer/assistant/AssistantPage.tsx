import { useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Button } from "@/components/ui/button";
import useAuthStore from "@/stores/authStore";
import { describeNodeFailure } from "@/components/laomedoErrors/nodeErrors";
import ErrorExplanation from "@/components/laomedoErrors/ErrorExplanation";
import { AssistantFailure, assistantRequest } from "./api";
import MessageRow from "./Message";
import type {
  ConversationDetail,
  ConversationIndex,
  Message,
  Models,
} from "./models";
import { stateLabel } from "./models";

export default function AssistantPage() {
  const owner = useAuthStore((state) => state.userData?.id);
  const [params, setParams] = useSearchParams();
  const selected = params.get("conversation") ?? "";
  const linked = params.get("linked") ?? "";
  const [index, setIndex] = useState<ConversationIndex>({
    conversations: [],
    next_cursor: null,
  });
  const [detail, setDetail] = useState<ConversationDetail>();
  const [models, setModels] = useState<Models>();
  const [model, setModel] = useState("");
  const [effort, setEffort] = useState("");
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [pending, setPending] = useState<
    Record<string, { id: string; text: string }>
  >({});
  const [error, setError] = useState<string>();
  const [locked, setLocked] = useState(false);
  const [busy, setBusy] = useState(false);
  const [history, setHistory] = useState(false);
  const [loading, setLoading] = useState(false);
  const generation = useRef(0);
  const scroll = useRef<HTMLDivElement>(null);
  const pinned = useRef(true);
  const currentSelection = useRef(selected);
  currentSelection.current = selected;

  const fail = useCallback((failure: unknown) => {
    const code =
      failure instanceof AssistantFailure
        ? failure.code
        : "assistant_connection_unavailable";
    setError(code);
    if (
      code === "assistant_session_locked" ||
      code === "assistant_native_session_required"
    ) {
      generation.current += 1;
      setLocked(true);
      setIndex({ conversations: [], next_cursor: null });
      setDetail(undefined);
      setDrafts({});
      setPending({});
    }
  }, []);

  const follow = useCallback(() => {
    if (pinned.current && scroll.current)
      scroll.current.scrollTop = scroll.current.scrollHeight;
  }, []);

  useEffect(() => {
    generation.current += 1;
    setLocked(false);
    setDetail(undefined);
    setDrafts({});
    setPending({});
    setError(undefined);
    setIndex({ conversations: [], next_cursor: null });
  }, [owner]);

  const refresh = useCallback(
    async (signal?: AbortSignal) => {
      const epoch = generation.current;
      const items = await assistantRequest<ConversationIndex>(
        "/conversations",
        undefined,
        signal,
      );
      if (signal?.aborted || epoch !== generation.current) return;
      setIndex((current) => ({
        ...items,
        conversations: [
          ...items.conversations,
          ...current.conversations.filter(
            (row) => !items.conversations.some((newer) => newer.id === row.id),
          ),
        ],
        next_cursor:
          current.conversations.length > 30
            ? current.next_cursor
            : items.next_cursor,
      }));
      if (selected) {
        const value = await assistantRequest<ConversationDetail>(
          `/conversations/${encodeURIComponent(selected)}`,
          undefined,
          signal,
        );
        if (
          signal?.aborted ||
          epoch !== generation.current ||
          currentSelection.current !== selected
        )
          return;
        setDetail((current) => {
          if (
            !current ||
            current.conversation.id !== value.conversation.id ||
            current.messages.length <= 30
          )
            return value;
          const messages = [
            ...current.messages.filter(
              (row) => !value.messages.some((newer) => newer.id === row.id),
            ),
            ...value.messages,
          ];
          return {
            ...value,
            messages,
            next_cursor: current.next_cursor === null ? null : messages.length,
            drafts: [
              ...value.drafts,
              ...current.drafts.filter(
                (row) => !value.drafts.some((newer) => newer.id === row.id),
              ),
            ],
          };
        });
        setPending((existing) => {
          const waiting = existing[selected];
          if (
            waiting &&
            value.messages.some(
              (message) => message.client_message_id === waiting.id,
            )
          ) {
            const next = { ...existing };
            delete next[selected];
            return next;
          }
          return existing;
        });
        requestAnimationFrame(follow);
      }
    },
    [selected, follow],
  );

  useEffect(() => {
    if (locked) return;
    const controller = new AbortController();
    let running = false;
    setDetail(undefined);
    setLoading(Boolean(selected));
    setError(undefined);
    pinned.current = true;
    const update = async () => {
      if (running) return;
      running = true;
      try {
        await refresh(controller.signal);
      } catch (failure) {
        if (!controller.signal.aborted) fail(failure);
      } finally {
        running = false;
        if (!controller.signal.aborted) setLoading(false);
      }
    };
    void update();
    const timer = window.setInterval(update, 1200);
    return () => {
      controller.abort();
      window.clearInterval(timer);
    };
  }, [refresh, selected, owner, locked, fail]);

  const discover = useCallback(async () => {
    const epoch = generation.current;
    setBusy(true);
    setError(undefined);
    try {
      const result = await assistantRequest<Models>("/models");
      if (epoch === generation.current) setModels(result);
    } catch (failure) {
      if (epoch === generation.current) fail(failure);
    } finally {
      if (epoch === generation.current) setBusy(false);
    }
  }, [fail]);

  useEffect(() => {
    if (!selected && !locked) void discover();
  }, [selected, locked, discover]);

  async function create() {
    const epoch = generation.current;
    setBusy(true);
    setError(undefined);
    try {
      const conversation = await assistantRequest<{ id: string }>(
        "/conversations",
        {
          provider: "codex",
          model,
          effort,
          ...(linked ? { linked_conversation_id: linked } : {}),
        },
      );
      if (epoch === generation.current)
        setParams({ conversation: conversation.id });
    } catch (failure) {
      if (epoch === generation.current) fail(failure);
    } finally {
      if (epoch === generation.current) setBusy(false);
    }
  }

  async function send() {
    const text = drafts[selected] ?? "";
    if (
      !text.trim() ||
      !detail ||
      detail.conversation.active_message_id ||
      pending[selected] ||
      busy
    )
      return;
    const epoch = generation.current;
    const identity = { id: crypto.randomUUID(), text };
    setPending((value) => ({ ...value, [selected]: identity }));
    setBusy(true);
    setError(undefined);
    pinned.current = true;
    try {
      await assistantRequest<Message>(`/conversations/${selected}/messages`, {
        client_message_id: identity.id,
        text,
      });
      if (epoch !== generation.current) return;
      setDrafts((value) => ({ ...value, [selected]: "" }));
      await refresh();
    } catch (failure) {
      if (epoch !== generation.current) return;
      fail(failure);
      // Retain the exact key on uncertain transport. Only an observation of that
      // client key clears it; no effect retries or new-key resubmission here.
      if (
        failure instanceof AssistantFailure &&
        failure.code !== "assistant_dispatch_unknown" &&
        failure.code !== "assistant_connection_unavailable"
      ) {
        setPending((value) => {
          const next = { ...value };
          delete next[selected];
          return next;
        });
      }
    } finally {
      if (epoch === generation.current) setBusy(false);
    }
  }

  async function stop() {
    const active = detail?.messages.find(
      (message) => message.id === detail.conversation.active_message_id,
    );
    if (!active || busy) return;
    const epoch = generation.current;
    setBusy(true);
    try {
      await assistantRequest(`/conversations/${selected}/stop`, {
        attempt_id: active.attempt_id,
      });
      if (epoch === generation.current) await refresh();
    } catch (failure) {
      if (epoch === generation.current) fail(failure);
    } finally {
      if (epoch === generation.current) setBusy(false);
    }
  }

  async function older() {
    if (!detail?.next_cursor) return;
    const epoch = generation.current,
      identity = selected;
    try {
      const page = await assistantRequest<ConversationDetail>(
        `/conversations/${identity}?cursor=${detail.next_cursor}`,
      );
      if (epoch !== generation.current || currentSelection.current !== identity)
        return;
      setDetail((current) =>
        current
          ? {
              ...current,
              messages: [
                ...page.messages.filter(
                  (row) =>
                    !current.messages.some((value) => value.id === row.id),
                ),
                ...current.messages,
              ],
              next_cursor: page.next_cursor,
            }
          : current,
      );
    } catch (failure) {
      if (epoch === generation.current) fail(failure);
    }
  }

  if (locked)
    return (
      <main className="m-auto max-w-lg space-y-4 p-8">
        <h1 className="text-xl font-semibold">Profile locked</h1>
        <p className="text-sm text-muted-foreground">
          Chat details are hidden and tool access has been revoked. Sign in
          through the existing profile screen to reopen your history.
        </p>
        <a
          href="/login"
          className="inline-block rounded-md border px-4 py-2 text-sm"
        >
          Unlock profile
        </a>
      </main>
    );
  const conversation = detail?.conversation;
  const active = Boolean(conversation?.active_message_id);
  const needsAttention = conversation?.state === "attention";
  const waiting = pending[selected];
  const canSend = Boolean(
    conversation &&
      conversation.state === "idle" &&
      !active &&
      !waiting &&
      !busy &&
      !detail?.observation_error &&
      !error,
  );
  const selectedModel = models?.models.find((item) => item.id === model);
  const explanation =
    error || detail?.observation_error || conversation?.error_code;
  const failure = explanation
    ? describeNodeFailure(explanation, undefined)
    : undefined;

  return (
    <main
      className="flex h-full min-h-0 w-full bg-background"
      aria-label="Application assistant"
    >
      <aside
        className={`${history ? "flex" : "hidden"} w-64 shrink-0 flex-col border-r bg-muted/20 p-4 md:flex`}
        aria-label="Conversations"
      >
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold">Conversations</h2>
          <button
            type="button"
            className="rounded px-2 py-1 text-sm md:hidden"
            onClick={() => setHistory(false)}
          >
            Close
          </button>
        </div>
        <Button
          className="my-4 w-full"
          variant="outline"
          onClick={() => {
            setParams({});
            setHistory(false);
          }}
        >
          New conversation
        </Button>
        <nav className="min-h-0 flex-1 space-y-1 overflow-y-auto">
          {index.conversations.map((item) => (
            <button
              key={item.id}
              type="button"
              aria-current={selected === item.id ? "page" : undefined}
              className={`w-full rounded-lg p-3 text-left text-sm hover:bg-muted focus-visible:outline focus-visible:outline-2 ${selected === item.id ? "bg-muted" : ""}`}
              onClick={() => {
                setParams({ conversation: item.id });
                setHistory(false);
              }}
            >
              <span className="block truncate font-medium">{item.title}</span>
              <span className="mt-1 block text-xs text-muted-foreground">
                Codex ·{" "}
                {item.active_message_id
                  ? stateLabel(item.state)
                  : new Date(item.updated_at * 1000).toLocaleDateString()}
              </span>
            </button>
          ))}
        </nav>
        <p className="mt-4 text-xs leading-relaxed text-muted-foreground">
          Switching conversations does not stop active work.
        </p>
      </aside>
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <header className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-b px-5 py-4">
          <div>
            <button
              type="button"
              onClick={() => setHistory(!history)}
              className="mb-2 text-sm underline md:hidden"
            >
              Conversations
            </button>
            <h1 className="text-lg font-semibold">
              {conversation?.title ?? "Laomedo assistant"}
            </h1>
            <p className="mt-1 text-xs text-muted-foreground">
              {conversation
                ? `Codex · ${conversation.model} · ${conversation.effort} · ${stateLabel(conversation.state)}`
                : "Create workflows in a normal conversation"}
            </p>
          </div>
          <a
            href="/flows"
            target="_blank"
            rel="noopener noreferrer"
            className="text-sm text-muted-foreground underline"
          >
            Workflows ↗
          </a>
        </header>
        {failure && (
          <div
            role="status"
            className="mx-5 mt-4 rounded-lg border bg-muted/30 p-4 text-sm"
          >
            <p className="mb-2 font-medium">
              {needsAttention
                ? "Cannot safely continue this session"
                : failure.title}
            </p>
            <ErrorExplanation failure={failure} />
            <div className="mt-3 flex flex-wrap gap-3">
              <button
                type="button"
                className="underline"
                onClick={() => {
                  setError(undefined);
                  void refresh().catch(fail);
                }}
              >
                Check status
              </button>
              {selected && (
                <button
                  type="button"
                  className="underline"
                  onClick={() => setParams({ linked: selected })}
                >
                  Start linked conversation
                </button>
              )}
            </div>
          </div>
        )}
        {!selected ? (
          <section className="m-auto w-full max-w-xl space-y-5 p-6">
            <h2 className="text-xl font-semibold">Start a conversation</h2>
            <p className="text-sm text-muted-foreground">
              Choose a model once for this conversation. Creating it does not
              send a prompt.
            </p>
            {linked && (
              <p className="text-xs text-muted-foreground">
                Linked to an earlier conversation. Its history remains
                available.
              </p>
            )}
            <div className="space-y-4 rounded-xl border p-5">
              <p className="text-sm">
                Provider <strong className="ml-3">Codex</strong>
              </p>
              <label className="block text-sm">
                Model
                <select
                  aria-label="Assistant model"
                  value={model}
                  onChange={(event) => {
                    setModel(event.target.value);
                    setEffort("");
                  }}
                  className="mt-2 block h-10 w-full rounded-md border bg-background px-3"
                >
                  <option value="">Select a model</option>
                  {models?.models.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.id}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block text-sm">
                Reasoning effort
                <select
                  aria-label="Assistant reasoning effort"
                  value={effort}
                  onChange={(event) => setEffort(event.target.value)}
                  className="mt-2 block h-10 w-full rounded-md border bg-background px-3"
                >
                  <option value="">Select an effort</option>
                  {selectedModel?.efforts.map((value) => (
                    <option key={value} value={value}>
                      {value}
                    </option>
                  ))}
                </select>
              </label>
              <Button disabled={busy || !model || !effort} onClick={create}>
                {busy ? "Checking availability…" : "Create conversation"}
              </Button>
              <button
                type="button"
                disabled={busy}
                className="ml-4 text-sm underline"
                onClick={discover}
              >
                Refresh models
              </button>
            </div>
          </section>
        ) : (
          <>
            <div
              ref={scroll}
              tabIndex={0}
              aria-label="Assistant messages and saved drafts"
              className="min-h-0 flex-1 overflow-y-auto px-5 py-6 focus-visible:outline focus-visible:outline-2 md:px-10"
              onScroll={() => {
                const element = scroll.current;
                if (element)
                  pinned.current =
                    element.scrollHeight -
                      element.scrollTop -
                      element.clientHeight <
                    100;
              }}
            >
              <div className="mx-auto max-w-4xl space-y-4 pb-8">
                {loading && (
                  <p role="status" className="text-sm text-muted-foreground">
                    Reconnecting to retained history…
                  </p>
                )}
                {detail?.next_cursor !== null &&
                  detail?.next_cursor !== undefined && (
                    <button
                      type="button"
                      className="text-sm underline"
                      onClick={older}
                    >
                      Load earlier messages
                    </button>
                  )}
                {detail?.messages.map((message) => (
                  <MessageRow
                    key={message.id}
                    conversation={selected}
                    message={message}
                    receipts={detail.drafts.filter(
                      (receipt) => receipt.message_id === message.id,
                    )}
                    active={conversation?.active_message_id === message.id}
                    onContent={follow}
                    onFailure={fail}
                  />
                ))}
                {waiting &&
                  !detail?.messages.some(
                    (row) => row.client_message_id === waiting.id,
                  ) && (
                    <div className="ml-auto max-w-[80%] rounded-xl border bg-muted/50 p-4">
                      <p className="mb-2 text-xs text-muted-foreground">
                        You · submission pending
                      </p>
                      <p className="whitespace-pre-wrap text-sm">
                        {waiting.text}
                      </p>
                    </div>
                  )}
                {detail && !detail.messages.length && (
                  <p className="pt-10 text-center text-sm text-muted-foreground">
                    Tell me what you want to build or change. I can inspect your
                    workflows and save a separate editable draft.
                  </p>
                )}
              </div>
            </div>
            <form
              className="shrink-0 border-t bg-background p-4 md:px-10"
              onSubmit={(event) => {
                event.preventDefault();
                void send();
              }}
            >
              <div className="mx-auto max-w-4xl">
                <label htmlFor="assistant-message" className="sr-only">
                  Message this assistant
                </label>
                <textarea
                  id="assistant-message"
                  maxLength={12000}
                  rows={3}
                  placeholder="Message this assistant…"
                  value={drafts[selected] ?? ""}
                  disabled={!canSend}
                  onChange={(event) =>
                    setDrafts((value) => ({
                      ...value,
                      [selected]: event.target.value,
                    }))
                  }
                  onKeyDown={(event) => {
                    if (
                      (event.ctrlKey || event.metaKey) &&
                      event.key === "Enter"
                    ) {
                      event.preventDefault();
                      void send();
                    }
                  }}
                  className="w-full resize-none rounded-lg border bg-background p-3 text-sm focus-visible:outline focus-visible:outline-2 disabled:opacity-60"
                />
                <div className="mt-2 flex items-center justify-between gap-3">
                  <p className="text-xs text-muted-foreground">
                    Ctrl+Enter sends · Drafts save without running
                  </p>
                  {active ? (
                    <Button
                      type="button"
                      variant="outline"
                      disabled={busy || conversation?.state === "stopping"}
                      onClick={stop}
                    >
                      {conversation?.state === "stopping"
                        ? "stopping…"
                        : "Stop response"}
                    </Button>
                  ) : (
                    <Button
                      type="submit"
                      disabled={!canSend || !(drafts[selected] ?? "").trim()}
                    >
                      Send
                    </Button>
                  )}
                </div>
              </div>
            </form>
          </>
        )}
      </div>
    </main>
  );
}
