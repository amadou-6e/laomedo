import { useEffect, useRef, useState, type CSSProperties } from "react";
import { createPortal } from "react-dom";
import RunnerRecovery from "./RunnerRecovery";
import { describeNodeFailure, type ErrorContext } from "@/components/laomedoErrors/nodeErrors";

// Fixed to the visible viewport, outside canvas transforms and clipping ancestors.
function viewportStyle(): CSSProperties {
  const viewport = window.visualViewport;
  const width = viewport?.width ?? window.innerWidth;
  const height = viewport?.height ?? window.innerHeight;
  return {
    position: "fixed", zIndex: 1000,
    right: `calc(${Math.max(0, window.innerWidth - ((viewport?.offsetLeft ?? 0) + width)) + 16}px + env(safe-area-inset-right, 0px))`,
    bottom: `calc(${Math.max(0, window.innerHeight - ((viewport?.offsetTop ?? 0) + height)) + 16}px + env(safe-area-inset-bottom, 0px))`,
    width: `min(384px, calc(${width}px - 32px - env(safe-area-inset-left, 0px) - env(safe-area-inset-right, 0px)))`,
    maxHeight: `calc(${height}px - 32px - env(safe-area-inset-top, 0px) - env(safe-area-inset-bottom, 0px))`,
    fontFamily: "Inter, Arial, sans-serif", fontSize: 14, lineHeight: "18px",
  };
}

export default function RecoveryPopup({ message, context, onDismiss }: {
  message: unknown; context: ErrorContext; onDismiss: () => void;
}) {
  const [style, setStyle] = useState(viewportStyle);
  const [copied, setCopied] = useState("");
  const root = useRef<HTMLElement>(null);
  const dismissRef = useRef(onDismiss);
  dismissRef.current = onDismiss;
  const failure = describeNodeFailure(message, undefined, context);
  const diagnostics = JSON.stringify(failure.diagnostics, null, 2);
  const name = (context.nodeLabel || context.nodeType || "Agent").replace(/^Laomedo\s*/, "").slice(0, 120);
  useEffect(() => {
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    root.current?.focus({ preventScroll: true });
    const update = () => setStyle(viewportStyle());
    const viewport = window.visualViewport;
    window.addEventListener("resize", update);
    viewport?.addEventListener("resize", update);
    viewport?.addEventListener("scroll", update);
    return () => {
      window.removeEventListener("resize", update);
      viewport?.removeEventListener("resize", update);
      viewport?.removeEventListener("scroll", update);
      if (previous?.isConnected) previous.focus({ preventScroll: true });
      else document.querySelector<HTMLElement>(".react-flow__pane")?.focus({ preventScroll: true });
    };
  }, []);
  const copy = async () => {
    try { await navigator.clipboard.writeText(diagnostics); setCopied("Copied"); }
    catch { setCopied("Copy unavailable. Select the details to copy them manually."); }
  };
  const buttonStyle: CSSProperties = { border: "1px solid currentColor", borderRadius: 3, background: "transparent", minHeight: 36, padding: "6px 16px", fontSize: 14, fontWeight: 700 };
  return createPortal(<RunnerRecovery message={message}>{recovery =>
    <section ref={root} tabIndex={-1} role="region" aria-label="Local backend recovery" style={style}
      onKeyDown={event => { if (event.key === "Escape") { event.stopPropagation(); dismissRef.current(); } }}
      className="flex min-h-0 flex-col overflow-hidden border border-slate-300 border-l-4 border-l-[#F87171] bg-background text-foreground shadow-sm focus:outline-none">
      <header className="flex shrink-0 flex-wrap items-baseline gap-x-1 gap-y-1 px-5 pb-2 pt-5">
        <h3 className="text-sm font-bold">{failure.title}</h3>
        <span className="min-w-0 break-words text-sm text-muted-foreground">· {name}{failure.diagnostics.operation ? ` / ${failure.diagnostics.operation}` : ""}</span>
      </header>
      <div className="min-h-0 overflow-y-auto overscroll-contain px-5" data-testid="recovery-popup-body">
        <p role="status">{recovery.state === "offline" && !recovery.waiting && !recovery.reason && !recovery.error
          ? "The local backend is offline. Your run may still be active." : recovery.message}</p>
        <p className="mt-2">Once reconnected, check the existing run.<br />Restarting does not rerun the graph.</p>
        {recovery.error && <p role="alert" className="mt-2">{recovery.error}</p>}
        <details className="mt-2 text-xs"><summary className="cursor-pointer">Technical details</summary>
          <pre style={{ fontFamily: "inherit" }} className="my-2 select-text whitespace-pre-wrap break-all text-xs">{diagnostics}</pre>
          <button type="button" onClick={copy} style={{ ...buttonStyle, fontSize: 12 }}>Copy diagnostics</button>
          {copied && <p role="status">{copied}</p>}
        </details>
      </div>
      <footer className="flex shrink-0 flex-wrap gap-3 px-5 pb-5 pt-3">
        {(recovery.canStart || recovery.waiting) && <button type="button" onClick={recovery.restart} disabled={recovery.waiting} style={{ ...buttonStyle, width: 196, maxWidth: "100%" }}
          className="disabled:opacity-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2">
          {recovery.waiting ? "Restarting..." : "Restart local backend"}
        </button>}
        <button type="button" onClick={onDismiss} style={{ ...buttonStyle, width: 112, maxWidth: "100%" }} className="focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2">Dismiss</button>
      </footer>
    </section>
  }</RunnerRecovery>, document.body);
}
