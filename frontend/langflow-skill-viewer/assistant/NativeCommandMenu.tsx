import { Fragment, useEffect, useId, useState } from "react";
import { BookOpen, ChevronRight, SquareTerminal } from "lucide-react";
import { assistantRequest } from "./api";
import type { NativeCommandCatalog } from "./models";
import { applicationCommands, providerCommandPreviews, nativeCommandText } from "./commandPreviews";

export default function NativeCommandMenu({ conversation, provider = "codex", runId, threadId, active = false, text, onSelect, onClose }: {
  conversation: string; provider?: string; runId?: string | null; threadId?: string | null; active?: boolean; text: string; onSelect: (value: string) => void; onClose: () => void;
}) {
  const [catalog, setCatalog] = useState<NativeCommandCatalog>();
  const [failed, setFailed] = useState(false);
  const [retry, setRetry] = useState(0);
  const reasonId = useId();
  useEffect(() => {
    if (!conversation) return;
    const controller = new AbortController();
    setCatalog(undefined);
    setFailed(false);
    void assistantRequest<NativeCommandCatalog>(`/conversations/${conversation}/native-commands`, undefined, controller.signal)
      .then(value => { if (!controller.signal.aborted) setCatalog(value); })
      .catch(() => { if (!controller.signal.aborted) setFailed(true); });
    return () => controller.abort();
  }, [conversation, provider, runId, threadId, active, retry]);
  const unstarted = !conversation || catalog?.reason === "native_session_not_created";
  const appCommands = applicationCommands[provider] ?? [];
  const nativeCommands = (unstarted
    ? (providerCommandPreviews[provider] ?? []).map(item => ({ ...item, executable: provider === "codex" && item.name === "status", reason: "native_session_not_created" }))
    : (catalog?.commands ?? [])
  ).filter(item => !appCommands.some(app => app.name === item.name)).map(item => ({...item, reason: ["plan", "goal"].includes(item.name) ? "deferred" : ["review-branch", "review-commit"].includes(item.name) ? "scratch_workspace" : item.reason}));
  const commands: NativeCommandCatalog["commands"] = [...nativeCommands, ...appCommands.map(item => ({...item, executable: item.action !== "rename" || Boolean(conversation), reason: "conversation_required"}))]
    .filter(item => (!text.startsWith("$") || item.name.startsWith("$")) && item.name.replace(/^\$/, "").toLowerCase().startsWith(text.slice(1).toLowerCase()))
    .sort((left, right) => Number(("kind" in left && left.kind) === "skill") - Number(("kind" in right && right.kind) === "skill") || Number(right.executable) - Number(left.executable));
  const hasBothGroups = commands.some(item => item.kind === "skill") && commands.some(item => item.kind !== "skill");
  const blockedLabel = (reason?: string | null) => reason === "native_session_not_created" ? "Start session"
    : reason === "conversation_required" ? "Needs conversation"
    : reason === "deferred" ? "Deferred"
    : reason === "scratch_workspace" || reason === "native_skill_requires_repository" ? "Needs repository"
    : reason === "outside_assistant_command_policy" ? "Not integrated"
    : reason === "native_skill_requires_provider_configuration" ? "App-managed settings"
    : reason === "native_skill_requires_subagents" ? "Needs subagents"
    : reason === "native_skill_requires_scheduling" ? "Needs scheduling"
    : reason === "native_skill_requires_external_services" ? "Needs services"
    : reason === "native_skill_source_unverified" ? "Source unverified"
    : reason === "native_skill_requirements_unverified" ? "Not verified"
    : "Unavailable";
  const unavailable = (reason?: string | null) => reason === "native_session_not_created"
    ? provider === "codex" ? "Start with /status; this command also needs native session support." : "Available after the first response, if supported by the native session."
    : reason === "conversation_required" ? "Create a conversation before renaming it."
    : reason === "deferred" ? "Plan mode and autonomous goals are deferred."
    : reason === "scratch_workspace" ? "Repository reviews are unavailable in this scratch workspace."
    : reason === "outside_assistant_command_policy" ? "This command needs a chat handler before it can run here."
    : reason === "native_skill_requires_provider_configuration" ? "This skill edits provider configuration, which is managed by Laomedo."
    : reason === "native_skill_requirements_unverified" ? "This bundled skill's required capabilities have not been verified for chat."
    : reason === "native_skill_source_unverified" ? "The native session has not verified this skill's bundled source."
    : reason === "native_skill_requires_subagents" ? "This skill requires native subagents, which are not available in this chat."
    : reason === "native_skill_requires_scheduling" ? "This skill requires scheduling or persistent execution, which is not available in this chat."
    : reason === "native_skill_requires_external_services" ? "This skill requires external services that are not connected to this chat."
    : reason === "native_skill_requires_repository" ? "This skill requires a repository; chat currently uses an isolated scratch workspace."
    : "This command is unavailable in this session.";
  return <div id="assistant-native-commands" aria-label="Available commands" className="absolute bottom-full left-0 right-0 z-20 mb-2 max-h-56 overflow-y-auto rounded-2xl border border-border/60 bg-muted p-1.5 text-xs shadow-lg"
    onKeyDown={event => {
      if (event.key === "Escape") { event.preventDefault(); onClose(); }
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        const buttons = Array.from(event.currentTarget.querySelectorAll("button:not(:disabled)"));
        const current = buttons.indexOf(document.activeElement as HTMLButtonElement);
        buttons[(current + (event.key === "ArrowDown" ? 1 : buttons.length - 1)) % buttons.length]?.focus();
      }
    }}>
    {conversation && failed && <button type="button" className="w-full px-2 py-1.5 text-left text-xs text-muted-foreground underline" onClick={() => setRetry(value => value + 1)}>Could not load native commands. Retry</button>}
    {conversation && !failed && !catalog && <p role="status" className="px-2 py-1.5 text-xs text-muted-foreground">Loading native commands…</p>}
    {commands.map((item, index) => <Fragment key={item.name}>
      {hasBothGroups && (index === 0 || (item.kind === "skill") !== (commands[index - 1].kind === "skill")) && <p className={`px-2 pb-1 pt-1 text-[10px] text-muted-foreground ${index > 0 ? "mt-1 border-t border-border/60 pt-2" : ""}`}>{item.kind === "skill" ? "Skills" : "Commands"}</p>}
      <button type="button" disabled={!item.executable} aria-describedby={!item.executable ? `${reasonId}-${index}` : undefined} title={item.executable ? item.description + (item.input_hint ? ` · Arguments: ${item.input_hint}` : "") : unavailable(item.reason)} className="group flex w-full min-w-0 items-center gap-2 rounded-lg px-2 py-1.5 text-left text-muted-foreground hover:bg-foreground/5 focus:bg-foreground/10 focus:outline-none disabled:opacity-50" onClick={() => onSelect(nativeCommandText(item.name) + " ")}>
      {item.kind === "skill" ? <BookOpen size={13} strokeWidth={1.5} aria-hidden="true" className="shrink-0 opacity-70" /> : <SquareTerminal size={13} strokeWidth={1.5} aria-hidden="true" className="shrink-0 opacity-70" />}
      <span className="shrink-0 font-medium text-foreground/80">{nativeCommandText(item.name)}</span><span className="min-w-0 flex-1 truncate text-[11px]">{item.description}{item.input_hint ? ` · ${item.input_hint}` : ""}</span>
      {!item.executable && <span className="shrink-0 text-[10px]">{blockedLabel(item.reason)}</span>}
      {!item.executable && <span id={`${reasonId}-${index}`} className="sr-only">{unavailable(item.reason)}</span>}
      <ChevronRight size={12} aria-hidden="true" className="shrink-0 opacity-0 group-hover:opacity-60 group-focus:opacity-60" />
    </button></Fragment>)}
    {commands.length === 1 && !commands[0].executable && <p className="px-2 py-1.5 text-[10px] text-muted-foreground">{unavailable(commands[0].reason)}</p>}
    {unstarted && provider === "codex" && commands.length > 0 && <p className="px-2 py-1.5 text-[10px] text-muted-foreground">Send /status to start a session without using the model. The session determines which other commands can run.</p>}
    {unstarted && provider !== "codex" && commands.length > 0 && <p className="px-2 py-1.5 text-[10px] text-muted-foreground">Start a chat to discover this session’s native commands.</p>}
    {!commands.length && <p className="px-3 py-2 text-xs text-muted-foreground">{unstarted ? provider === "codex" ? "No matching command. Press Enter to send this as a chat message." : "Commands become available after the first response in this conversation." : catalog?.state === "unavailable" ? "Native commands are unavailable in this session." : failed ? "Could not load commands. Type / again to retry." : !catalog ? "Loading commands…" : "No matching command. Press Enter to send this as a chat message."}</p>}
  </div>;
}
