import { useEffect, useState } from "react";
import { assistantRequest } from "./api";
import type { NativeCommandCatalog } from "./models";

export default function NativeCommandMenu({ conversation, text, onSelect, onClose }: {
  conversation: string; text: string; onSelect: (value: string) => void; onClose: () => void;
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
  return <div id="assistant-native-commands" aria-label="Available commands" className="mb-2 max-h-56 overflow-y-auto rounded-xl border bg-background p-1 text-sm shadow-lg"
    onKeyDown={event => {
      if (event.key === "Escape") { event.preventDefault(); onClose(); }
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        const buttons = Array.from(event.currentTarget.querySelectorAll("button"));
        const current = buttons.indexOf(document.activeElement as HTMLButtonElement);
        buttons[(current + (event.key === "ArrowDown" ? 1 : buttons.length - 1)) % buttons.length]?.focus();
      }
    }}>
    {commands.map(item => <button key={item.name} type="button" className="block w-full rounded-lg px-3 py-2 text-left hover:bg-muted focus:bg-muted focus:outline-none" onClick={() => onSelect(`/${item.name} `)}>
      <span className="font-medium">/{item.name}</span><span className="ml-3 text-xs text-muted-foreground">{item.description}</span>
    </button>)}
    {!commands.length && <p className="px-3 py-2 text-xs text-muted-foreground">{!conversation || catalog?.state === "unavailable" ? "Commands become available after the first response in this conversation." : failed ? "Could not load commands. Type / again to retry." : !catalog ? "Loading commands…" : "No matching commands."}</p>}
  </div>;
}
