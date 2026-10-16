import { useEffect, useRef, useState, type ReactNode } from "react";

export default function SkillSplitPane({ navigation, children }: { navigation: ReactNode; children: ReactNode }) {
  const container = useRef<HTMLDivElement>(null);
  const pointer = useRef<number | null>(null);
  const [width, setWidth] = useState(280);
  const [maximum, setMaximum] = useState(600);
  const [dragging, setDragging] = useState(false);
  const clamp = (value: number) => Math.max(180, Math.min(maximum, value));
  useEffect(() => {
    const resize = () => {
      const limit = Math.max(180, Math.min(600, (container.current?.getBoundingClientRect().width || 880) - 280));
      setMaximum(limit); setWidth((current) => Math.max(180, Math.min(limit, current)));
    };
    resize();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(resize);
    observer.observe(container.current!);
    return () => observer.disconnect();
  }, []);
  return <div ref={container} className="flex min-h-0 min-w-0 flex-1" style={{ userSelect: dragging ? "none" : undefined }}>
    <aside aria-label="Skill navigation" className="flex min-h-0 shrink-0 flex-col pr-2" style={{ width }}>
      {navigation}
    </aside>
    <div role="separator" aria-label="Resize navigation pane" aria-orientation="vertical" aria-valuemin={180}
      aria-valuemax={maximum} aria-valuenow={Math.round(width)} tabIndex={0}
      className="mx-1 w-1.5 shrink-0 cursor-col-resize touch-none rounded bg-border/50 hover:bg-primary/30 focus-visible:bg-primary/30 focus-visible:outline-none"
      onPointerDown={(event) => {
        if (event.button !== 0) return;
        pointer.current = event.pointerId; setDragging(true);
        event.currentTarget.setPointerCapture(event.pointerId); event.preventDefault();
      }}
      onPointerMove={(event) => {
        if (pointer.current !== event.pointerId) return;
        setWidth(clamp(event.clientX - (container.current?.getBoundingClientRect().left || 0)));
      }}
      onPointerUp={(event) => {
        if (pointer.current !== event.pointerId) return;
        pointer.current = null; setDragging(false);
        if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
      }}
      onPointerCancel={() => { pointer.current = null; setDragging(false); }}
      onLostPointerCapture={() => { pointer.current = null; setDragging(false); }}
      onKeyDown={(event) => {
        if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
        event.preventDefault();
        const step = event.shiftKey ? 64 : 16;
        setWidth((current) => event.key === "Home" ? 180 : event.key === "End" ? maximum : clamp(current + (event.key === "ArrowLeft" ? -step : step)));
      }} />
    <div className="flex min-h-0 min-w-0 flex-1 pl-2">{children}</div>
  </div>;
}
