import SkillActions from "./SkillActions";
import { useEffect, useRef, useState, type ReactNode } from "react";

export default function SkillSplitPane({ navigation, children }: { navigation: ReactNode; children: ReactNode }) {
  const container = useRef<HTMLDivElement>(null);
  const separator = useRef<HTMLDivElement>(null);
  const lastWidth = useRef(280);
  const pointer = useRef<number | null>(null);
  const [width, setWidth] = useState(280);
  const [maximum, setMaximum] = useState(600);
  const [dragging, setDragging] = useState(false);
  const clamp = (value: number) => value < 90 ? 0 : Math.max(180, Math.min(maximum, value));
  useEffect(() => {
    const resize = () => {
      const limit = Math.max(180, Math.min(600, (container.current?.getBoundingClientRect().width || 880) - 280));
      setMaximum(limit); setWidth((current) => current === 0 ? 0 : Math.max(180, Math.min(limit, current)));
    };
    resize();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(resize);
    observer.observe(container.current!);
    return () => observer.disconnect();
  }, []);
  useEffect(() => { if (width > 0) lastWidth.current = width; }, [width]);
  const collapse = () => { setWidth(0); separator.current?.focus(); };
  const restore = () => { setWidth(clamp(lastWidth.current)); separator.current?.focus(); };
  return <div ref={container} className="flex min-h-0 min-w-0 flex-1" style={{ userSelect: dragging ? "none" : undefined }}>
    <aside aria-label="Skill navigation" className="flex min-h-0 shrink-0 flex-col border-r bg-muted/20" style={{ width, display: width === 0 ? "none" : undefined }}>
      <div className="flex h-8 shrink-0 items-center justify-between px-2 text-xs tracking-wide text-muted-foreground">
        <span>SKILL</span>
        <SkillActions label="Navigation actions">
            <button type="button" className="w-full px-2 py-1 text-left text-sm hover:bg-muted" onClick={collapse}>Hide navigation</button>
            <button type="button" className="w-full px-2 py-1 text-left text-sm hover:bg-muted" onClick={() => setWidth(clamp(280))}>Reset navigation width</button>
        </SkillActions>
      </div>
      {navigation}
    </aside>
    <div ref={separator} role="separator" aria-label="Resize navigation pane" aria-orientation="vertical" aria-valuemin={0}
      aria-valuemax={maximum} aria-valuenow={Math.round(width)} aria-valuetext={width === 0 ? "Navigation collapsed" : `${Math.round(width)} pixels`} title="Drag left to collapse; drag right to restore. Double-click to toggle." tabIndex={0}
      className="w-1.5 shrink-0 cursor-col-resize touch-none bg-border/50 hover:bg-primary/30 focus-visible:bg-primary/30 focus-visible:outline-none"
      onDoubleClick={() => width === 0 ? restore() : collapse()}
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
        setWidth((current) => event.key === "Home" ? 0 : event.key === "End" ? maximum : (current === 0 && event.key === "ArrowRight" ? clamp(lastWidth.current) : current <= 180 && event.key === "ArrowLeft" ? 0 : clamp(current + (event.key === "ArrowLeft" ? -step : step))));
      }} />
    <div className="relative flex min-h-0 min-w-0 flex-1 flex-col pl-2">
      {width === 0 && <button type="button" onClick={restore} className="mb-1 self-start rounded px-2 py-1 text-xs hover:bg-muted" aria-label="Show skill navigation">Show navigation</button>}
      {children}
    </div>
  </div>;
}
