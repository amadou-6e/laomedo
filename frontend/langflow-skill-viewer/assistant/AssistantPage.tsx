import { useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  Plus,
  ChevronLeft,
  ChevronRight,
  ArrowUp,
  Square,
  Workflow,
  MessageSquare,
  Check,
  Sparkles,
} from "lucide-react";
import { OpenAiIcon } from "@/icons/OpenAi";
import { Button } from "@/components/ui/button";
import useAuthStore from "@/stores/authStore";
import { describeNodeFailure } from "@/components/laomedoErrors/nodeErrors";
import ErrorExplanation from "@/components/laomedoErrors/ErrorExplanation";
import { AssistantFailure, assistantRequest } from "./api";
import MessageRow, { UserMessage } from "./Message";
import Thinking from "./Thinking";
import ModelSelection from "./ModelSelection";
import type {
  ConversationDetail,
  Conversation,
  ConversationIndex,
  Message,
  Models,
  PendingSubmission,
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
  const [pending, setPending] = useState<Record<string, PendingSubmission>>({});
  const [retryable, setRetryable] = useState<Record<string, boolean>>({});
  const [pendingOwner, setPendingOwner] = useState<string>();
  const previousOwner = useRef<string | undefined>(undefined);
  const [error, setError] = useState<string>();
  const [locked, setLocked] = useState(false);
  const [busy, setBusy] = useState(false);
  const [history, setHistory] = useState(true);
  const [renaming, setRenaming] = useState<string>();
  const [titleDraft, setTitleDraft] = useState("");
  const [savingTitle, setSavingTitle] = useState(false);
  const [renameError, setRenameError] = useState(false);
  const [loading, setLoading] = useState(false);
  const generation = useRef(0);
  const scroll = useRef<HTMLDivElement>(null);
  const pinned = useRef(true);
  const currentSelection = useRef(selected);
  currentSelection.current = selected;

  useEffect(() => {
    setRenaming(undefined);
    setTitleDraft("");
    setRenameError(false);
  }, [selected, owner, locked]);

  const fail = useCallback(
    (failure: unknown) => {
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
        setRetryable({});
        try {
          if (owner)
            sessionStorage.removeItem(`laomedo.assistant.pending.${owner}`);
        } catch {
          /* Rendered private state is already cleared. */
        }
      }
    },
    [owner],
  );

  const follow = useCallback(() => {
    if (pinned.current && scroll.current)
      scroll.current.scrollTop = scroll.current.scrollHeight;
  }, []);

  useEffect(() => {
    generation.current += 1;
    setLocked(false);
    setDetail(undefined);
    setModels(undefined);
    setModel("");
    setEffort("");
    boundSelection.current = "";
    setDrafts({});
    setPending({});
    setRetryable({});
    setPendingOwner(undefined);
    try {
      if (previousOwner.current && previousOwner.current !== owner)
        sessionStorage.removeItem(
          `laomedo.assistant.pending.${previousOwner.current}`,
        );
    } catch {
      /* No storage access may block a profile fence. */
    }
    previousOwner.current = owner;
    if (owner) {
      try {
        const restored = JSON.parse(
          sessionStorage.getItem(`laomedo.assistant.pending.${owner}`) ?? "{}",
        );
        if (
          restored &&
          typeof restored === "object" &&
          !Array.isArray(restored) &&
          Object.values(restored).every(
            (row: any) =>
              typeof row?.id === "string" &&
              /^[0-9a-f-]{36}$/.test(row.id) &&
              typeof row?.text === "string" &&
              row.text.length <= 12000 &&
              ((row.model === undefined && row.effort === undefined) ||
                (typeof row.model === "string" &&
                  typeof row.effort === "string")),
          )
        ) {
          setPending(restored);
          setRetryable(
            Object.fromEntries(
              Object.values(restored).map((row: any) => [row.id, true]),
            ),
          );
        }
      } catch {
        /* Sending verifies stable retention before dispatch. */
      }
      setPendingOwner(owner);
    }
    setError(undefined);
    setIndex({ conversations: [], next_cursor: null });
  }, [owner]);

  useEffect(() => {
    if (owner && pendingOwner === owner && !locked) {
      try {
        sessionStorage.setItem(
          `laomedo.assistant.pending.${owner}`,
          JSON.stringify(pending),
        );
      } catch {
        /* Sending verifies retention. */
      }
    }
  }, [owner, pendingOwner, pending, locked]);

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
          ...items.conversations.map((row) => {
            const retained = current.conversations.find(
              (item) => item.id === row.id,
            );
            return retained && retained.updated_at > row.updated_at
              ? retained
              : row;
          }),
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
            current?.conversation.id === value.conversation.id &&
            current.conversation.updated_at > value.conversation.updated_at
          )
            value.conversation = current.conversation;
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
    if (!locked) void discover();
  }, [selected, locked, discover]);

  const boundSelection = useRef("");
  useEffect(() => {
    if (!selected) {
      boundSelection.current = "";
    } else if (
      detail?.conversation.id === selected &&
      boundSelection.current !== selected
    ) {
      boundSelection.current = selected;
      setModel(detail.conversation.model);
      setEffort(detail.conversation.effort);
    }
  }, [selected, detail?.conversation.id]);

  useEffect(() => {
    if (selected || !models) return;
    const recent = index.conversations.find((conversation) =>
      models.models.some(
        (choice) =>
          choice.id === conversation.model &&
          choice.efforts.includes(conversation.effort),
      ),
    );
    const choice =
      models.models.find((item) => item.id === model && item.efforts.length) ??
      models.models.find((item) => item.id === recent?.model) ??
      models.models.find((item) => item.efforts.length);
    if (!choice) return;
    setModel(choice.id);
    setEffort(
      choice.efforts.includes(effort)
        ? effort
        : recent && choice.id === recent.model
          ? recent.effort
          : choice.efforts[0],
    );
  }, [selected, models, model, effort, index.conversations]);

  async function create() {
    return assistantRequest<{ id: string }>("/conversations", {
      provider: "codex",
      model,
      effort,
      ...(linked ? { linked_conversation_id: linked } : {}),
    });
  }

  async function send(retry?: PendingSubmission) {
    const text = retry?.text ?? drafts[selected] ?? "";
    if (
      !text.trim() ||
      (selected && (!detail || detail.conversation.active_message_id)) ||
      (!retry && (!model || !effort)) ||
      (pending[selected] && !retry) ||
      busy
    )
      return;
    const epoch = generation.current;
    const identity = retry ?? { id: crypto.randomUUID(), text, model, effort };
    let target = selected;
    let acknowledged = false;
    if (
      retry &&
      (pending[selected]?.id !== retry.id ||
        pending[selected]?.text !== retry.text ||
        pending[selected]?.model !== retry.model ||
        pending[selected]?.effort !== retry.effort)
    )
      return;
    setBusy(true);
    setRetryable((value) => ({ ...value, [identity.id]: false }));
    setError(undefined);
    pinned.current = true;
    try {
      if (!target) {
        const created = await create();
        if (
          epoch !== generation.current ||
          currentSelection.current !== selected
        )
          return;
        target = created.id;
      }
      try {
        sessionStorage.setItem(
          `laomedo.assistant.pending.${owner}`,
          JSON.stringify({ ...pending, [target]: identity }),
        );
      } catch {
        throw new AssistantFailure("assistant_client_state_unavailable");
      }
      setPending((value) => ({ ...value, [target]: identity }));
      setDrafts((value) => ({ ...value, [selected]: "" }));
      requestAnimationFrame(follow);
      if (!selected) setParams({ conversation: target });
      await assistantRequest<Message>(`/conversations/${target}/messages`, {
        client_message_id: identity.id,
        text: identity.text,
        model: identity.model,
        effort: identity.effort,
      });
      acknowledged = true;
      if (epoch !== generation.current) return;
      if (target === selected) await refresh();
    } catch (failure) {
      if (epoch !== generation.current) return;
      fail(failure);
      if (epoch !== generation.current) return;
      if (acknowledged) return;
      // Retain the exact key on uncertain transport. Only an observation of that
      // client key clears it; no effect retries or new-key resubmission here.
      if (
        failure instanceof AssistantFailure &&
        failure.code !== "assistant_dispatch_unknown" &&
        failure.code !== "assistant_connection_unavailable"
      ) {
        setPending((value) => {
          const next = { ...value };
          delete next[target];
          return next;
        });
        setDrafts((value) => ({ ...value, [target]: identity.text }));
      } else {
        setRetryable((value) => ({ ...value, [identity.id]: true }));
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

  async function olderConversations() {
    if (index.next_cursor === null) return;
    const epoch = generation.current;
    try {
      const page = await assistantRequest<ConversationIndex>(
        `/conversations?cursor=${index.next_cursor}`,
      );
      if (epoch !== generation.current) return;
      setIndex((current) => ({
        ...page,
        conversations: [
          ...current.conversations,
          ...page.conversations.filter(
            (row) =>
              !current.conversations.some((existing) => existing.id === row.id),
          ),
        ],
      }));
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
    (!selected || conversation?.state === "idle") &&
      model &&
      effort &&
      !active &&
      !waiting &&
      !busy &&
      !detail?.observation_error &&
      !error,
  );
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
      <div
        className={`relative min-h-0 shrink-0 ${history ? "w-64 max-w-[75vw]" : "w-5"}`}
      >
        <aside
          hidden={!history}
          className={`${history ? "flex" : "hidden"} h-full flex-col bg-muted/20 p-4 pr-6`}
          aria-label="Conversations"
        >
          <h2 className="mb-4 text-sm font-semibold">Conversations</h2>
          <nav className="min-h-0 flex-1 space-y-1 overflow-y-auto">
            {index.conversations.map((item) => (
              <button
                key={item.id}
                type="button"
                aria-current={selected === item.id ? "page" : undefined}
                className={`w-full rounded-lg p-3 text-left text-sm hover:bg-muted focus-visible:outline focus-visible:outline-2 ${selected === item.id ? "bg-muted" : ""}`}
                onClick={() => {
                  setParams({ conversation: item.id });
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
          {index.next_cursor !== null && (
            <button
              type="button"
              className="mt-3 text-left text-sm underline"
              onClick={() => void olderConversations()}
            >
              Load earlier conversations
            </button>
          )}
          <p className="mt-4 text-xs leading-relaxed text-muted-foreground">
            Switching conversations does not stop active work.
          </p>
          <Button
            className="mt-4 w-full justify-start"
            variant="ghost"
            aria-label="New conversation"
            onClick={() => setParams({})}
          >
            <Plus size={16} />
            New conversation
          </Button>
        </aside>
        <button
          type="button"
          aria-label={
            history ? "Collapse conversations" : "Expand conversations"
          }
          title={history ? "Collapse conversations" : "Expand conversations"}
          aria-expanded={history}
          onClick={() => setHistory(!history)}
          className="absolute inset-y-0 right-0 flex w-4 items-center justify-center border-r text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline focus-visible:outline-2"
        >
          {history ? <ChevronLeft size={12} /> : <ChevronRight size={12} />}
        </button>
      </div>
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <header className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-b px-5 py-4">
          <div className="min-w-0 flex-1">
            {renaming === conversation?.id && conversation ? (
              <form
                onSubmit={async (event) => {
                  event.preventDefault();
                  if (savingTitle || !titleDraft.trim()) return;
                  const identifier = conversation.id;
                  const version = generation.current;
                  setSavingTitle(true);
                  setRenameError(false);
                  try {
                    const renamed = await assistantRequest<Conversation>(
                      `/conversations/${identifier}`,
                      { title: titleDraft },
                      undefined,
                      "PATCH",
                    );
                    if (version !== generation.current) return;
                    setIndex((current) => ({
                      ...current,
                      conversations: current.conversations.map((row) =>
                        row.id === identifier ? renamed : row,
                      ),
                    }));
                    setDetail((current) =>
                      current?.conversation.id === identifier
                        ? { ...current, conversation: renamed }
                        : current,
                    );
                    setRenaming(undefined);
                  } catch (error) {
                    if (version === generation.current) {
                      if (
                        error instanceof AssistantFailure &&
                        [
                          "assistant_session_locked",
                          "assistant_native_session_required",
                        ].includes(error.code)
                      )
                        fail(error);
                      else setRenameError(true);
                    }
                  } finally {
                    setSavingTitle(false);
                  }
                }}
                className="flex w-full items-center gap-2"
              >
                <input
                  autoFocus
                  aria-label="Conversation title"
                  value={titleDraft}
                  maxLength={80}
                  disabled={savingTitle}
                  onChange={(event) => setTitleDraft(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Escape") setRenaming(undefined);
                  }}
                  className="min-w-0 flex-1 rounded border bg-background px-2 py-1 text-sm"
                />
                <button
                  type="submit"
                  disabled={savingTitle || !titleDraft.trim()}
                  className="text-xs"
                >
                  {savingTitle ? "Saving…" : "Save"}
                </button>
                <button
                  type="button"
                  disabled={savingTitle}
                  onClick={() => setRenaming(undefined)}
                  className="text-xs text-muted-foreground"
                >
                  Cancel
                </button>
                {renameError && (
                  <span role="alert" className="text-xs text-destructive">
                    Could not rename. Try again.
                  </span>
                )}
              </form>
            ) : (
              <h1
                className="inline text-sm font-medium"
                onDoubleClick={() => {
                  if (conversation) {
                    setTitleDraft(conversation.title);
                    setRenaming(conversation.id);
                  }
                }}
              >
                <button
                  type="button"
                  disabled={!conversation}
                  title="Double-click to rename conversation"
                  onKeyDown={(event) => {
                    if (conversation && ["Enter", " "].includes(event.key)) {
                      event.preventDefault();
                      setTitleDraft(conversation.title);
                      setRenaming(conversation.id);
                    }
                  }}
                >
                  {conversation?.title ?? "Laomedo assistant"}
                </button>
              </h1>
            )}
          </div>
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
              {loading && !waiting && (
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
                  <section
                    className="space-y-5 pb-6"
                    aria-label="Message and response"
                  >
                    <UserMessage text={waiting.text} />
                    {retryable[waiting.id] && !busy && !loading ? (
                      <div>
                        <button
                          type="button"
                          disabled={busy || active}
                          className="mt-3 text-sm underline"
                          onClick={() => void send(waiting)}
                        >
                          Retry same submission
                        </button>
                        <p className="mt-1 text-xs text-muted-foreground">
                          Reuses its original message ID. Accepted messages are
                          observed rather than dispatched again.
                        </p>
                      </div>
                    ) : (
                      <Thinking />
                    )}
                  </section>
                )}
              {!waiting &&
                (!selected || (detail && !detail.messages.length)) && (
                  <div className="mx-auto w-full max-w-md space-y-5 py-10 text-center">
                    <div
                      aria-hidden="true"
                      className="relative mx-auto flex h-24 w-64 items-center justify-center gap-4 rounded-full bg-gradient-to-r from-transparent via-primary/10 to-transparent"
                    >
                      <span className="-rotate-6 rounded-2xl border bg-background p-3 text-muted-foreground shadow-sm">
                        <MessageSquare size={22} />
                      </span>
                      <span className="h-px w-5 bg-primary/40" />
                      <span className="relative rounded-2xl border border-primary/30 bg-primary/10 p-4 text-primary shadow-sm">
                        <Workflow size={32} />
                        <Sparkles
                          size={15}
                          className="absolute -right-2 -top-2"
                        />
                      </span>
                      <span className="h-px w-5 bg-primary/40" />
                      <span className="rotate-6 rounded-2xl border bg-background p-3 text-muted-foreground shadow-sm">
                        <Check size={22} />
                      </span>
                    </div>
                    <h2 className="text-xl font-medium">
                      What would you like to build?
                    </h2>
                    <p className="text-sm text-muted-foreground">
                      Describe a workflow or ask me to change one. I can inspect
                      workflows and save a separate editable draft.
                    </p>
                    {!selected && (
                      <fieldset
                        className="pt-2 text-left"
                        aria-label="Assistant provider"
                      >
                        <label className="flex cursor-default items-center gap-4 rounded-2xl border border-primary/40 bg-primary/5 p-4 has-[:focus-visible]:outline has-[:focus-visible]:outline-2">
                          <input
                            type="radio"
                            name="assistant-provider"
                            aria-label="Codex"
                            checked
                            readOnly
                            className="sr-only"
                          />
                          <span aria-hidden="true" className="text-4xl">
                            <OpenAiIcon />
                          </span>
                          <span className="min-w-0 flex-1">
                            <span className="block text-sm font-medium">
                              Codex
                            </span>
                            <span className="mt-1 block text-xs text-muted-foreground">
                              OpenAI · Your workflow-building companion
                            </span>
                          </span>
                          <span className="inline-flex items-center gap-1 text-xs text-primary">
                            <Check size={14} />
                            Selected
                          </span>
                        </label>
                      </fieldset>
                    )}
                    {linked && (
                      <p className="text-xs text-muted-foreground">
                        Linked to an earlier conversation. Its history remains
                        available.
                      </p>
                    )}
                  </div>
                )}
            </div>
          </div>
          <form
            className="shrink-0 bg-background px-4 pb-4 pt-2 md:px-10"
            onSubmit={(event) => {
              event.preventDefault();
              void send();
            }}
          >
            <div className="mx-auto max-w-4xl rounded-2xl border bg-muted/30 p-2 shadow-sm focus-within:ring-1 focus-within:ring-ring">
              <label htmlFor="assistant-message" className="sr-only">
                Message this assistant
              </label>
              <textarea
                id="assistant-message"
                maxLength={12000}
                rows={2}
                placeholder={
                  selected ? "Message this assistant…" : "Start chat…"
                }
                value={drafts[selected] ?? ""}
                disabled={
                  busy ||
                  active ||
                  Boolean(selected && (!detail || needsAttention || waiting))
                }
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
                className="block w-full resize-none border-0 bg-transparent px-2 py-2 text-sm outline-none placeholder:text-muted-foreground disabled:opacity-60"
              />
              <div className="mt-1 flex items-center justify-end gap-2 px-1">
                <ModelSelection
                  models={models}
                  model={model}
                  effort={effort}
                  disabled={busy || active || Boolean(waiting)}
                  onModel={(value) => {
                    const next = models?.models.find(
                      (item) => item.id === value,
                    );
                    setModel(value);
                    setEffort(
                      next?.efforts.includes(effort)
                        ? effort
                        : (next?.efforts[0] ?? ""),
                    );
                  }}
                  onEffort={setEffort}
                />
                {active ? (
                  <button
                    type="button"
                    aria-label="Stop response"
                    title={
                      conversation?.state === "stopping"
                        ? "Stopping…"
                        : "Stop response"
                    }
                    disabled={busy || conversation?.state === "stopping"}
                    onClick={stop}
                    className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-foreground text-background disabled:opacity-40"
                  >
                    <Square size={12} fill="currentColor" />
                  </button>
                ) : (
                  <button
                    type="submit"
                    aria-label={selected ? "Send" : "Start chat"}
                    title={
                      selected ? "Send (Ctrl+Enter)" : "Start chat (Ctrl+Enter)"
                    }
                    disabled={!canSend || !(drafts[selected] ?? "").trim()}
                    className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-foreground text-background transition-opacity disabled:opacity-30"
                  >
                    <ArrowUp size={17} />
                  </button>
                )}
              </div>
            </div>
          </form>
        </>
      </div>
    </main>
  );
}
