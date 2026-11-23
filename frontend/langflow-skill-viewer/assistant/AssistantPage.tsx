import useConversationExport from "./conversation/useConversationExport";
import useSavedAccounts from "./composer/useSavedAccounts";
import useModelDiscovery from "./composer/useModelDiscovery";
import MessageList from "./messages/MessageList";
import ConversationHistory from "./history/ConversationHistory";
import Composer from "./composer/Composer";
import Welcome from "./conversation/Welcome";
import ConversationTitle from "./conversation/ConversationTitle";
import ProjectStorage from "./storage/ProjectStorage";
import {
  applicationCommands,
  providerCommandNames,
  codexBundledSkillNames,
  codexSkillMentions,
} from "./commands/commandPreviews";
import GraphPermissions from "./graphs/GraphPermissions";
import {
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
  type FormEvent,
} from "react";
import { useLocation, useSearchParams } from "react-router-dom";
import { Download, History } from "lucide-react";
import { AuthContext } from "@/contexts/authContext";
import { describeNodeFailure } from "@/components/laomedoErrors/nodeErrors";
import ErrorExplanation from "@/components/laomedoErrors/ErrorExplanation";
import { AssistantFailure, assistantRequest } from "./api";
import type {
  ConversationDetail,
  Conversation,
  ConversationIndex,
  Message,
  PendingSubmission,
  NativeCommandCatalog,
} from "./models";
import DeleteConversation from "./conversation/DeleteConversation";

export default function AssistantPage({
  embedded = false,
  selectedConversation,
  linkedConversation,
  onSelectConversation,
  headerActions,
}: {
  embedded?: boolean;
  headerActions?: ReactNode;
  selectedConversation?: string;
  linkedConversation?: string;
  onSelectConversation?: (selection: Record<string, string>) => void;
} = {}) {
  const RootTag = embedded ? "section" : "main";
  const activeGraphId = useLocation().pathname.match(/^\/flow\/([^/]+)\/?$/)?.[1];
  const owner = useContext(AuthContext).userData?.id;
  const [params, setRouteParams] = useSearchParams();
  const selected = embedded
    ? (selectedConversation ?? "")
    : (params.get("conversation") ?? "");
  const linked = embedded
    ? (linkedConversation ?? "")
    : (params.get("linked") ?? "");
  const setParams = (selection: Record<string, string>) => {
    if (embedded) onSelectConversation?.(selection);
    else setRouteParams(selection);
  };
  const [index, setIndex] = useState<ConversationIndex>({
    conversations: [],
    next_cursor: null,
  });
  const [detail, setDetail] = useState<ConversationDetail>();
  const [provider, setProvider] = useState("codex");
  const selectedProvider =
    detail?.conversation.id === selected
      ? detail.conversation.provider
      : index.conversations.find((item) => item.id === selected)?.provider;
  const providerKnown = !selected || Boolean(selectedProvider);
  const chosenProvider = selected ? (selectedProvider ?? "codex") : provider;
  const providerRef = useRef(chosenProvider);
  providerRef.current = chosenProvider;
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const retainSettingsDraft = (nextDrafts = drafts) => {
    if (!owner || locked) return false;
    try {
      sessionStorage.setItem(
        `laomedo.assistant.settings-drafts.${owner}`,
        JSON.stringify({ drafts: nextDrafts, provider }),
      );
      return true;
    } catch {
      return window.confirm(
        "Your draft could not be saved. Leave chat and discard it?",
      );
    }
  };
  const [pending, setPending] = useState<Record<string, PendingSubmission>>({});
  const [retryable, setRetryable] = useState<Record<string, boolean>>({});
  const [pendingOwner, setPendingOwner] = useState<string>();
  const previousOwner = useRef<string | undefined>(undefined);
  const [error, setError] = useState<string>();
  const [locked, setLocked] = useState(false);
  const [busy, setBusy] = useState(false);
  const [commandsDismissed, setCommandsDismissed] = useState(false);
  const [history, setHistory] = useState(!embedded);
  const [renaming, setRenaming] = useState<string>();
  const [titleDraft, setTitleDraft] = useState("");
  const [savingTitle, setSavingTitle] = useState(false);
  const [renameError, setRenameError] = useState(false);
  const [loading, setLoading] = useState(false);
  const generation = useRef(0);
  const scroll = useRef<HTMLDivElement>(null);
  const pinned = useRef(true);
  const currentSelection = useRef(selected);
  const nativeSubmission = useRef<{
    conversation: string;
    text: string;
    request: {
      name: string;
      arguments: string;
      catalog_revision: string;
      operation_key: string;
    };
  } | undefined>(undefined);
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
          if (owner)
            sessionStorage.removeItem(
              `laomedo.assistant.settings-drafts.${owner}`,
            );
        } catch {
          /* Rendered private state is already cleared. */
        }
      }
    },
    [owner],
  );

  const { accounts, accountsLoading, accountsOwner, account, setAccount } =
    useSavedAccounts({ owner, locked, selected, chosenProvider, fail });
  const boundAccount = selected
    ? detail?.conversation.id === selected
      ? detail.conversation
      : index.conversations.find((item) => item.id === selected)
    : undefined;
  const connectionId =
    owner && accountsOwner === owner
      ? selected
        ? boundAccount?.connection_id
        : account?.provider === chosenProvider
          ? account.connection_id
          : undefined
      : undefined;
  const connectionGeneration =
    owner && accountsOwner === owner
      ? selected
        ? boundAccount?.connection_generation
        : account?.provider === chosenProvider
          ? account.generation
          : undefined
      : undefined;
  const binding = `${chosenProvider}:${connectionId ?? ""}:${connectionGeneration ?? ""}`;
  const bindingRef = useRef(binding);
  bindingRef.current = binding;

  const { exporting, exportError, exportConversation, exportController } =
    useConversationExport({
      selected,
      owner,
      locked,
      generation,
      currentSelection,
      fail,
    });

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
      if (previousOwner.current && previousOwner.current !== owner)
        sessionStorage.removeItem(
          `laomedo.assistant.settings-drafts.${previousOwner.current}`,
        );
    } catch {
      /* No storage access may block a profile fence. */
    }
    previousOwner.current = owner;
    if (owner) {
      try {
        const key = `laomedo.assistant.settings-drafts.${owner}`;
        const retained = JSON.parse(sessionStorage.getItem(key) ?? "null");
        sessionStorage.removeItem(key);
        if (
          retained &&
          ["codex", "claude", "opencode"].includes(retained.provider) &&
          retained.drafts &&
          typeof retained.drafts === "object" &&
          !Array.isArray(retained.drafts) &&
          Object.entries(retained.drafts).every(
            ([key, text]) =>
              (key === "" || /^[0-9a-f-]{36}$/.test(key)) &&
              typeof text === "string" &&
              text.length <= 12000,
          )
        ) {
          setDrafts(retained.drafts);
          setProvider(retained.provider);
        }
      } catch {
        /* Corrupt or unavailable browser storage never changes admission. */
      }
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
              (row.initial_native_command === undefined ||
                (row.initial_native_command === "status" &&
                  row.text === "/status")) &&
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

  const {
    models,
    setModels,
    model,
    setModel,
    effort,
    setEffort,
    discovering,
    boundSelection,
  } = useModelDiscovery({
    selected,
    locked,
    providerKnown,
    chosenProvider,
    connectionId,
    connectionGeneration,
    binding,
    generation,
    bindingRef,
    fail,
    clearError: () => setError(undefined),
    detail,
    index,
  });

  async function create() {
    return assistantRequest<{ id: string }>("/conversations", {
      provider,
      connection_id: connectionId,
      connection_generation: connectionGeneration,
      model,
      effort,
      ...(linked ? { linked_conversation_id: linked } : {}),
    });
  }

  function clearCommandInputError() {
    setError((value) =>
      value &&
      [
        "native_command_not_available",
        "native_command_not_supported",
        "native_command_arguments_invalid",
        "native_command_catalog_changed",
        "native_skill_approval_required",
      ].includes(value)
        ? undefined
        : value,
    );
  }

  async function send(retry?: PendingSubmission) {
    if (!retry && appCommand && canUseAppCommand) {
      const nextDrafts = { ...drafts, [selected]: "" };
      if (appCommand.action === "accounts") {
        if (retainSettingsDraft(nextDrafts))
          window.location.assign("/settings/providers");
      } else if (conversation) {
        setTitleDraft(conversation.title);
        setRenaming(conversation.id);
        setDrafts(nextDrafts);
        setCommandsDismissed(true);
      }
      return;
    }
    if (!retry && !canSend) return;
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
    const initialStatus =
      text.trim() === "/status" &&
      chosenProvider === "codex" &&
      (!selected ||
        (detail?.conversation.id === selected && !detail.conversation.run_id));
    const identity: PendingSubmission = retry ?? {
      id: crypto.randomUUID(),
      text: initialStatus ? "/status" : text,
      model,
      effort,
      ...(initialStatus ? { initial_native_command: "status" as const } : {}),
    };
    let target = selected;
    let acknowledged = false;
    if (
      retry &&
      (pending[selected]?.id !== retry.id ||
        pending[selected]?.text !== retry.text ||
        pending[selected]?.model !== retry.model ||
        pending[selected]?.effort !== retry.effort ||
        pending[selected]?.initial_native_command !==
          retry.initial_native_command)
    )
      return;
    setBusy(true);
    setRetryable((value) => ({ ...value, [identity.id]: false }));
    setError(undefined);
    pinned.current = true;
    try {
      if (
        (text.startsWith("/") ||
          (chosenProvider === "codex" && text.startsWith("$"))) &&
        !identity.initial_native_command
      ) {
        let submission = nativeSubmission.current;
        if (
          !submission ||
          submission.conversation !== target ||
          submission.text !== text
        ) {
          submission = undefined;
          const parsed = /^([/$])([^\s]+)(?: (.*))?$/.exec(text);
          const match = parsed
            ? [parsed[0], (parsed[1] === "$" ? "$" : "") + parsed[2], parsed[3]]
            : null;
          if (
            chosenProvider === "codex" &&
            codexSkillMentions(text).some((name) => name !== match?.[1])
          )
            throw new AssistantFailure("native_skill_approval_required");
          if (
            text.startsWith("$") &&
            codexBundledSkillNames.includes(match?.[1] ?? "") &&
            (!target || !detail?.conversation.run_id)
          )
            throw new AssistantFailure("native_command_not_available");
          if (
            (!target || !detail?.conversation.run_id) &&
            (providerCommandNames[chosenProvider] ?? []).includes(
              match?.[1] ?? "",
            )
          ) {
            throw new AssistantFailure("native_command_not_available");
          }
          if (target && match) {
            const catalog = await assistantRequest<NativeCommandCatalog>(
              `/conversations/${target}/native-commands`,
            );
            if (
              epoch !== generation.current ||
              currentSelection.current !== target
            )
              return;
            const command = catalog.commands?.find(
              (item) => item.name === match[1],
            );
            if (
              (catalog.state !== "available" &&
                catalog.reason !== "native_session_not_created") ||
              (!command &&
                (providerCommandNames[chosenProvider] ?? []).includes(match[1]))
            ) {
              throw new AssistantFailure("native_command_not_available");
            }
            if (command && !command.executable)
              throw new AssistantFailure("native_command_not_supported");
            if (command) {
              const args = match[2] ?? "";
              if (!catalog.revision || (args && !command.accepts_arguments))
                throw new AssistantFailure("native_command_arguments_invalid");
              submission = {
                conversation: target,
                text,
                request: {
                  name: command.name,
                  arguments: args,
                  catalog_revision: catalog.revision,
                  operation_key: crypto.randomUUID(),
                },
              };
              nativeSubmission.current = submission;
            }
          }
        }
        if (submission) {
          await assistantRequest(
            `/conversations/${target}/native-commands`,
            submission.request,
          );
          if (
            epoch !== generation.current ||
            currentSelection.current !== target
          )
            return;
          nativeSubmission.current = undefined;
          setDrafts((value) => ({
            ...value,
            [target]: value[target] === text ? "" : (value[target] ?? ""),
          }));
          await refresh();
          return;
        }
      }
      if (chosenProvider === "codex" && codexSkillMentions(text).length)
        throw new AssistantFailure("native_skill_approval_required");
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
      setDrafts((value) => {
        const nextDraft =
          value[selected] === text ? "" : (value[selected] ?? "");
        return { ...value, [selected]: "", [target]: nextDraft };
      });
      requestAnimationFrame(follow);
      if (!selected) setParams({ conversation: target });
      await assistantRequest<Message>(`/conversations/${target}/messages`, {
        client_message_id: identity.id,
        text: identity.text,
        model: identity.model,
        effort: identity.effort,
        ...(identity.initial_native_command
          ? { initial_native_command: identity.initial_native_command }
          : {}),
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
        setDrafts((value) => ({
          ...value,
          [target]:
            value[target] && value[target] !== identity.text
              ? `${identity.text}\n\n${value[target]}`
              : identity.text,
        }));
      } else {
        setRetryable((value) => ({ ...value, [identity.id]: true }));
      }
    } finally {
      if (epoch === generation.current) setBusy(false);
    }
  }

  async function saveTitle(event: FormEvent) {
    if (!conversation) return;
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
      <RootTag className="m-auto max-w-lg space-y-4 p-8">
        {headerActions && (
          <div className="flex justify-end gap-2">{headerActions}</div>
        )}
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
      </RootTag>
    );
  const historyControl = embedded && (
    <button
      type="button"
      aria-label={history ? "Collapse conversations" : "Expand conversations"}
      title={history ? "Collapse conversations" : "Expand conversations"}
      aria-expanded={history}
      onClick={() => setHistory(!history)}
      className="rounded p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground focus-visible:outline focus-visible:outline-2"
    >
      <History size={16} aria-hidden="true" />
    </button>
  );
  const conversation = detail?.conversation;
  const active = Boolean(conversation?.active_message_id);
  const needsAttention = conversation?.state === "attention";
  const waiting = pending[selected];
  const providerName =
    (
      { codex: "Codex", claude: "Claude", opencode: "OpenCode" } as Record<
        string,
        string
      >
    )[chosenProvider] ?? chosenProvider;
  const providerAccounts = accounts.filter(
    (item) =>
      item.provider === chosenProvider && item.lifecycle === "connected",
  );
  const composerStatus = error
    ? undefined
    : accountsLoading
      ? "Loading accounts…"
      : !providerAccounts.length
        ? `Connect a ${providerName} account in Settings → Providers to chat.`
        : !connectionId
          ? undefined
          : discovering
            ? `Loading ${providerName} models…`
            : models && !models.models.length
              ? "No models were returned for this account."
              : undefined;
  const canSend = Boolean(
    connectionId &&
      connectionGeneration &&
      accounts.some(
        (item) =>
          item.connection_id === connectionId &&
          item.generation === connectionGeneration &&
          item.lifecycle === "connected",
      ) &&
      (!selected || conversation?.state === "idle") &&
      model &&
      effort &&
      !active &&
      !waiting &&
      !busy &&
      !discovering &&
      !detail?.observation_error &&
      ![
        "assistant_dispatch_unknown",
        "assistant_connection_unavailable",
      ].includes(error ?? ""),
  );
  const appCommand = (applicationCommands[chosenProvider] ?? []).find(
    (item) => `/${item.name}` === (drafts[selected] ?? "").trim(),
  );
  const canUseAppCommand = Boolean(
    appCommand &&
      owner &&
      !locked &&
      !busy &&
      !active &&
      !waiting &&
      !needsAttention &&
      (appCommand.action !== "rename" || conversation),
  );
  const explanation =
    error || detail?.observation_error || conversation?.error_code;
  const failure = explanation
    ? describeNodeFailure(explanation, undefined)
    : undefined;

  return (
    <RootTag
      className="flex h-full min-h-0 w-full bg-background"
      aria-label="Application assistant"
    >
      <ConversationHistory
        index={index}
        onIndex={setIndex}
        generation={generation}
        owner={owner}
        selected={selected}
        embedded={embedded}
        history={history}
        historyControl={historyControl}
        headerActions={headerActions}
        fail={fail}
        onSelect={(id) => {
          setParams({ conversation: id });
          if (embedded) setHistory(false);
        }}
        onNew={() => {
          setParams({});
          if (embedded) setHistory(false);
        }}
        onToggle={() => setHistory(!history)}
      />
      <div
        hidden={embedded && history}
        className={`${embedded && history ? "hidden" : "flex"} min-h-0 min-w-0 flex-1 flex-col`}
      >
        <header
          className={`flex shrink-0 flex-wrap items-center justify-between border-b ${embedded ? "min-h-11 gap-2 px-3 py-2" : "gap-3 px-5 py-4"}`}
        >
          <div className="min-w-0 flex-1">
            <ConversationTitle
              conversation={conversation}
              renaming={renaming === conversation?.id}
              titleDraft={titleDraft}
              savingTitle={savingTitle}
              renameError={renameError}
              onSave={saveTitle}
              onDraft={setTitleDraft}
              onCancel={() => setRenaming(undefined)}
              onRename={() => {
                if (conversation) {
                  setTitleDraft(conversation.title);
                  setRenaming(conversation.id);
                }
              }}
            />
          </div>
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            {historyControl}
            {!locked && <ProjectStorage key={owner} activeGraphId={activeGraphId} onFailure={fail} />}
            {conversation && !locked && (
              <>
                <span role="status" aria-live="polite">
                  {exporting
                    ? "Exporting..."
                    : exportError
                      ? "Export failed. Try again."
                      : ""}
                </span>
                <button
                  type="button"
                  aria-label="Export conversation"
                  title="Export conversation as Markdown"
                  disabled={exporting}
                  onClick={() => void exportConversation()}
                  className="rounded p-1.5 hover:bg-muted hover:text-foreground disabled:opacity-40 focus-visible:outline focus-visible:outline-2"
                >
                  <Download size={16} />
                </button>
                <DeleteConversation
                  key={`${owner}:${selected}`}
                  conversation={selected}
                  title={conversation.title}
                  onFailure={fail}
                  onDeleted={() => {
                    generation.current += 1;
                    exportController.current?.abort();
                    setIndex((value) => ({
                      ...value,
                      conversations: value.conversations.filter(
                        (row) => row.id !== selected,
                      ),
                    }));
                    setDetail(undefined);
                    setDrafts((value) => {
                      const next = { ...value };
                      delete next[selected];
                      return next;
                    });
                    setPending((value) => {
                      const next = { ...value };
                      delete next[selected];
                      return next;
                    });
                    setRetryable((value) => {
                      const next = { ...value };
                      if (pending[selected]) delete next[pending[selected].id];
                      return next;
                    });
                    setParams({});
                  }}
                />
              </>
            )}
            {headerActions}
          </div>
        </header>
        {failure && (
          <div
            role="status"
            className="mx-5 mt-4 rounded-lg border bg-muted/30 p-4 text-sm"
          >
            <p className="mb-2 font-medium">
              {needsAttention &&
              failure.diagnostics.code !== "runner_authentication_required"
                ? "This session needs attention"
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
            className="min-h-0 flex-1 overflow-y-auto px-5 pt-6 pb-2 focus-visible:outline focus-visible:outline-2 md:px-10"
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
            <div className="mx-auto max-w-4xl space-y-4">
              {selected && (
                <GraphPermissions
                  conversation={selected}
                  permissions={detail?.permissions ?? []}
                  onChange={() => void refresh().catch(fail)}
                  onFailure={fail}
                />
              )}
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
              <MessageList
                conversationId={selected}
                provider={conversation?.provider ?? "codex"}
                detail={detail}
                activeMessageId={conversation?.active_message_id}
                failureShown={Boolean(failure)}
                explanation={explanation}
                waiting={waiting}
                retryable={Boolean(waiting && retryable[waiting.id])}
                busy={busy}
                active={active}
                loading={loading}
                onContent={follow}
                onFailure={fail}
                onRetry={(submission) => void send(submission)}
              />
              {!waiting &&
                (!selected || (detail && !detail.messages.length)) && (
                  <Welcome
                    selected={selected}
                    linked={linked}
                    provider={provider}
                    pending={Boolean(pending[""])}
                    onProvider={(id) => {
                      setProvider(id);
                      setAccount(undefined);
                      setModels(undefined);
                      setModel("");
                      setEffort("");
                      setError(undefined);
                    }}
                  />
                )}
            </div>
          </div>
          <Composer
            selected={selected}
            provider={chosenProvider}
            runId={conversation?.run_id}
            threadId={conversation?.thread_id}
            active={active}
            stopping={conversation?.state === "stopping"}
            busy={busy}
            text={drafts[selected] ?? ""}
            readOnly={locked || Boolean(selected && needsAttention)}
            canSubmit={canSend || canUseAppCommand}
            commandsDismissed={commandsDismissed}
            accountsLoading={accountsLoading}
            hasAccounts={Boolean(providerAccounts.length)}
            hasConnection={Boolean(connectionId)}
            composerStatus={composerStatus}
            onDraft={(text) => {
              clearCommandInputError();
              setDrafts((value) => ({ ...value, [selected]: text }));
            }}
            onDismissCommands={setCommandsDismissed}
            onSend={() => void send()}
            onStop={() => void stop()}
            accountSelection={{
              onManageAccounts: retainSettingsDraft,
              provider: chosenProvider,
              accounts: accounts.filter(
                (item) => item.provider === chosenProvider,
              ),
              selected: connectionId,
              generation: connectionGeneration,
              loading: accountsLoading,
              disabled: Boolean(selected || busy || active || pending[""]),
              onSelect: (value) => {
                if (
                  value.connection_id === connectionId &&
                  value.generation === connectionGeneration
                )
                  return;
                setAccount(value);
                setModels(undefined);
                setModel("");
                setEffort("");
                setError(undefined);
              },
            }}
            modelSelection={{
              models,
              model: connectionId ? model : "",
              effort: connectionId ? effort : "",
              disabled:
                !connectionId ||
                !models?.models.length ||
                busy ||
                discovering ||
                active ||
                Boolean(waiting),
              onModel: (value) => {
                const next = models?.models.find((item) => item.id === value);
                setModel(value);
                setEffort(
                  next?.efforts.includes(effort)
                    ? effort
                    : (next?.efforts[0] ?? ""),
                );
              },
              onEffort: setEffort,
            }}
          />
        </>
      </div>
    </RootTag>
  );
}
