import { useEffect, useState } from "react";
import { ChevronRight, SquareTerminal } from "lucide-react";
import { assistantRequest } from "./api";
import type { NativeCommandCatalog } from "./models";

export default function NativeCommandMenu({ conversation, provider = "codex", text, onSelect, onClose }: {
  conversation: string; provider?: string; text: string; onSelect: (value: string) => void; onClose: () => void;
}) {
  const [catalog, setCatalog] = useState<NativeCommandCatalog>();
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    if (!conversation) return;
    const controller = new AbortController();
    setCatalog(undefined);
    setFailed(false);
    void assistantRequest<NativeCommandCatalog>(`/conversations/${conversation}/native-commands`, undefined, controller.signal)
      .then(value => { if (!controller.signal.aborted) setCatalog(value); })
      .catch(() => { if (!controller.signal.aborted) setFailed(true); });
    return () => controller.abort();
  }, [conversation]);
  const commands = (catalog?.commands ?? []).filter(item => item.executable && item.name.toLowerCase().startsWith(text.slice(1).toLowerCase()));
  const unstarted = !conversation || catalog?.reason === "native_session_not_created";
  return <div id="assistant-native-commands" aria-label="Available commands" className="absolute bottom-full left-0 right-0 z-20 mb-2 max-h-56 overflow-y-auto rounded-2xl border border-border/60 bg-muted p-1.5 text-xs shadow-lg"
    onKeyDown={event => {
      if (event.key === "Escape") { event.preventDefault(); onClose(); }
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        const buttons = Array.from(event.currentTarget.querySelectorAll("button"));
        const current = buttons.indexOf(document.activeElement as HTMLButtonElement);
        buttons[(current + (event.key === "ArrowDown" ? 1 : buttons.length - 1)) % buttons.length]?.focus();
      }
    }}>
    {commands.length > 0 && <p className="px-2 pb-1 pt-1 text-[10px] text-muted-foreground">Commands</p>}
    {commands.map(item => <button key={item.name} type="button" title={item.description} className="group flex w-full min-w-0 items-center gap-2 rounded-lg px-2 py-1.5 text-left text-muted-foreground hover:bg-foreground/5 focus:bg-foreground/10 focus:outline-none" onClick={() => onSelect(`/${item.name} `)}>
      <SquareTerminal size={13} strokeWidth={1.5} aria-hidden="true" className="shrink-0 opacity-70" />
      <span className="shrink-0 font-medium text-foreground/80">/{item.name}</span><span className="min-w-0 flex-1 truncate text-[11px]">{item.description}</span>
      <ChevronRight size={12} aria-hidden="true" className="shrink-0 opacity-0 group-hover:opacity-60 group-focus:opacity-60" />
    </button>)}
    {!commands.length && <p className="px-3 py-2 text-xs text-muted-foreground">{unstarted ? provider === "codex" ? "Send /status to start a session without using the model." : "Commands become available after the first response in this conversation." : catalog?.state === "unavailable" ? "Native commands are unavailable in this session." : failed ? "Could not load commands. Type / again to retry." : !catalog ? "Loading commands…" : "No matching commands."}</p>}
  </div>;
}
