import { useEffect, useRef, useState } from "react";
import { ExternalLink, ChevronRight } from "lucide-react";
import { Link } from "react-router-dom";
import useAuthStore from "@/stores/authStore";
import AssistantPage from "../AssistantPage";
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
  const drag = useRef({ start: 0, moved: false });
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
  return <aside id="laomedo-assistant-sidebar" ref={container} hidden={!open} aria-label="Assistant sidebar" className={`${open ? "flex" : "hidden"} ${overlay ? "absolute right-0 z-50 shadow-xl" : "relative z-30"} h-full min-h-0 shrink-0 flex-col border-l bg-background pl-2`} style={{ width, maxWidth: "100%" }}>
    <div role="separator" aria-label="Resize assistant" aria-orientation="vertical" aria-valuemin={280} aria-valuemax={maximum} aria-valuenow={width} tabIndex={0}
      className="absolute inset-y-0 left-0 z-10 w-2 cursor-col-resize touch-none border-r text-muted-foreground hover:bg-muted focus-visible:bg-primary/20 focus-visible:outline focus-visible:outline-2"
      onPointerDown={(event) => { drag.current = { start: event.clientX, moved: false }; event.preventDefault(); event.currentTarget.focus(); event.currentTarget.querySelector("button")?.setPointerCapture(event.pointerId); }}
      onPointerMove={(event) => { if (event.currentTarget.querySelector("button")?.hasPointerCapture(event.pointerId)) { if (Math.abs(event.clientX - drag.current.start) > 3) drag.current.moved = true; resize((container.current?.getBoundingClientRect().right ?? event.clientX) - event.clientX); } }}
      onPointerUp={(event) => { const handle = event.currentTarget.querySelector("button"); if (handle?.hasPointerCapture(event.pointerId)) handle.releasePointerCapture(event.pointerId); }}
      onKeyDown={(event) => {
        if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
        event.preventDefault();
        resize(event.key === "Home" ? 280 : event.key === "End" ? maximum : width + (event.key === "ArrowLeft" ? 24 : -24));
      }}>
      <button type="button" aria-label="Collapse assistant sidebar" title="Drag to resize; click to collapse" className="flex h-full w-full cursor-col-resize items-center justify-center hover:text-foreground focus-visible:outline focus-visible:outline-2" onClick={(event) => {if (event.detail !== 0 && drag.current.moved) { drag.current.moved = false; return; } setOpen(false);window.requestAnimationFrame(() => { const opener = document.getElementById("laomedo-assistant-opener"); if (opener && !opener.closest('[aria-hidden="true"], [hidden], [inert]')) opener.focus(); });}}><ChevronRight size={8} aria-hidden="true" /></button>
    </div>
    <div className="min-h-0 flex-1">{mounted && <AssistantPage headerActions={<Link to={fullChat} aria-label="Open full-window assistant" title="Open full-window assistant" className="rounded p-1 text-muted-foreground hover:text-foreground focus-visible:outline"><ExternalLink size={16} /></Link>} embedded selectedConversation={selection.conversation} linkedConversation={selection.linked} onSelectConversation={setSelection} />}</div>
  </aside>;
}
