import { useEffect, useRef, useState } from "react";
import { ExternalLink, X } from "lucide-react";
import useAuthStore from "@/stores/authStore";
import AssistantPage from "./AssistantPage";
import { useAssistantSidebarStore } from "./sidebarStore";

export default function AssistantSidebar() {
  const { open, setOpen } = useAssistantSidebarStore();
  const owner = useAuthStore((state) => state.userData?.id);
  const [mounted, setMounted] = useState(false);
  const [selection, setSelection] = useState<Record<string, string>>({});
  const [width, setWidth] = useState(480);
  const [maximum, setMaximum] = useState(720);
  const [overlay, setOverlay] = useState(false);
  const container = useRef<HTMLElement>(null);
  const previousOwner = useRef(owner);
  useEffect(() => { if (open) setMounted(true); }, [open]);
  useEffect(() => {
    if (previousOwner.current !== owner) {
      setSelection({});
      setMounted(false);
      setOpen(false);
      previousOwner.current = owner;
    }
  }, [owner, setOpen]);
  useEffect(() => {
    const parent = container.current?.parentElement;
    if (!parent) return;
    const resize = () => {
      const available = parent.clientWidth;
      setOverlay(available < 960);
      const limit = Math.max(280, Math.min(720, available < 960 ? available - 32 : available - 320));
      setMaximum(limit);
      setWidth((current) => Math.min(limit, Math.max(280, current)));
    };
    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(parent);
    return () => observer.disconnect();
  }, []);
  const resize = (next: number) => setWidth(Math.min(maximum, Math.max(280, next)));
  const fullChat = selection.conversation ? `/assistant?conversation=${encodeURIComponent(selection.conversation)}` : "/assistant";
  return <aside id="laomedo-assistant-sidebar" ref={container} hidden={!open} aria-label="Assistant sidebar" className={`${open ? "flex" : "hidden"} ${overlay ? "absolute right-0 z-50 shadow-xl" : "relative z-30"} h-full min-h-0 shrink-0 flex-col border-l bg-background`} style={{ width, maxWidth: "100%" }}>
    <div role="separator" aria-label="Resize assistant" aria-orientation="vertical" aria-valuemin={280} aria-valuemax={maximum} aria-valuenow={width} tabIndex={0}
      className="absolute inset-y-0 -left-1 z-10 w-2 cursor-col-resize touch-none hover:bg-primary/20 focus-visible:bg-primary/20 focus-visible:outline focus-visible:outline-2"
      onPointerDown={(event) => { event.preventDefault(); event.currentTarget.focus(); event.currentTarget.setPointerCapture(event.pointerId); }}
      onPointerMove={(event) => { if (event.currentTarget.hasPointerCapture(event.pointerId)) resize((container.current?.getBoundingClientRect().right ?? event.clientX) - event.clientX); }}
      onPointerUp={(event) => { if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId); }}
      onKeyDown={(event) => {
        if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
        event.preventDefault();
        resize(event.key === "Home" ? 280 : event.key === "End" ? maximum : width + (event.key === "ArrowLeft" ? 24 : -24));
      }} />
    <header className="flex h-11 shrink-0 items-center gap-2 border-b px-4 text-sm">
      <span className="flex-1 font-medium">Assistant</span>
      <a href={fullChat} target="_blank" rel="noopener noreferrer" aria-label="Open assistant in a new tab" title="Open assistant in a new tab" className="rounded p-1 text-muted-foreground hover:text-foreground focus-visible:outline"><ExternalLink size={16} /></a>
      <button type="button" aria-label="Close assistant" title="Close assistant" className="rounded p-1 text-muted-foreground hover:text-foreground focus-visible:outline" onClick={() => {setOpen(false);window.requestAnimationFrame(() => document.getElementById("laomedo-assistant-opener")?.focus());}}><X size={16} /></button>
    </header>
    <div className="min-h-0 flex-1">{mounted && <AssistantPage embedded selectedConversation={selection.conversation} linkedConversation={selection.linked} onSelectConversation={setSelection} />}</div>
  </aside>;
}
