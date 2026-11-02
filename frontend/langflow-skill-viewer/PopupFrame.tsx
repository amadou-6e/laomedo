import { useEffect, useLayoutEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { createPortal } from "react-dom";
export const popupButtonStyle: CSSProperties = { border: "1px solid currentColor", borderRadius: 3, background: "transparent", minHeight: 36, padding: "6px 16px", fontSize: 14, fontWeight: 700 };
const stacks = new WeakMap<HTMLElement, { element: HTMLElement; users: number }>();
let dialogStackId = 0;
function viewportStyle(): CSSProperties {
  const v = window.visualViewport, w = v?.width ?? window.innerWidth, h = v?.height ?? window.innerHeight;
  return { position: "fixed", zIndex: 1000,
    right: `calc(${Math.max(0, window.innerWidth - ((v?.offsetLeft ?? 0) + w)) + 16}px + env(safe-area-inset-right, 0px))`,
    bottom: `calc(${Math.max(0, window.innerHeight - ((v?.offsetTop ?? 0) + h)) + 16}px + env(safe-area-inset-bottom, 0px))`,
    width: `min(384px, calc(${w}px - 32px - env(safe-area-inset-left, 0px) - env(safe-area-inset-right, 0px)))`,
    maxHeight: `calc(${h}px - 32px - env(safe-area-inset-top, 0px) - env(safe-area-inset-bottom, 0px))`,
    display: "flex", flexDirection: "column", gap: "12px", overflowY: "auto", fontFamily: "Inter, Arial, sans-serif", fontSize: "14px", lineHeight: "18px" };
}
// Shared viewport-bound stack, outside canvas transforms and clipping ancestors.
export default function PopupFrame({ label, heading, children, footer, onClose, autoFocus = true, code, nodeId, operation, tools, recovered = false }: {
  label: string; heading: ReactNode; tools?: ReactNode; children: ReactNode; footer: ReactNode; onClose: () => void; autoFocus?: boolean; code?: string; nodeId?: string; operation?: string; recovered?: boolean;
}) {
  const [host, setHost] = useState<HTMLElement | null>(null), root = useRef<HTMLElement>(null), anchor = useRef<HTMLSpanElement>(null);
  useLayoutEffect(() => {
    // Keep modal errors inside its focus/inert boundary. A manual popover puts
    // that descendant in the top layer, outside clipping/transform ancestors.
    const owner = anchor.current?.closest<HTMLElement>('[role="dialog"]') || document.body;
    let entry = stacks.get(owner);
    if (!entry) {
      const element = document.createElement("div");
      element.id = owner === document.body ? "laomedo-error-popup-stack" : `laomedo-dialog-error-popup-stack-${++dialogStackId}`;
      owner.appendChild(element); entry = { element, users: 0 }; stacks.set(owner, entry);
      if (owner !== document.body && typeof element.showPopover === "function") {
        element.setAttribute("popover", "manual"); element.showPopover();
      }
    }
    const stack = entry.element; entry.users++;
    stack.setAttribute("role", "region"); stack.setAttribute("aria-label", "Error notifications");
    stack.setAttribute("aria-live", "assertive"); stack.setAttribute("aria-relevant", "additions");
    const update = () => Object.assign(stack.style, { inset: "auto", margin: "0", padding: "0", border: "0", background: "transparent", pointerEvents: "auto" }, viewportStyle());
    update(); setHost(stack); const v = window.visualViewport;
    window.addEventListener("resize", update); v?.addEventListener("resize", update); v?.addEventListener("scroll", update);
    return () => { window.removeEventListener("resize", update); v?.removeEventListener("resize", update); v?.removeEventListener("scroll", update); if (--entry!.users === 0) { stack.remove(); stacks.delete(owner); } };
  }, []);
  useEffect(() => {
    if (!host || !autoFocus) return;
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null, card = root.current;
    card?.focus({ preventScroll: true });
    return () => { if (card?.contains(document.activeElement) || document.activeElement === document.body) {
      if (previous?.isConnected) previous.focus({ preventScroll: true }); else document.querySelector<HTMLElement>(".react-flow__pane")?.focus({ preventScroll: true });
    } };
  }, [host, autoFocus]);
  return <><span ref={anchor} hidden />{host && createPortal(<section ref={root} tabIndex={-1} role="region" aria-label={label} data-error-code={code} data-error-node={nodeId} data-error-operation={operation} style={{ maxHeight: "inherit", borderLeftColor: recovered ? "#4ADE80" : "#F87171" }}
    onKeyDown={event => { if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); event.nativeEvent.stopImmediatePropagation(); onClose(); } }}
    className="flex min-h-0 shrink-0 flex-col overflow-hidden border border-slate-300 border-l-4 border-l-[#F87171] bg-background text-foreground shadow-sm focus:outline-none">
    <header className={`relative flex shrink-0 flex-wrap items-baseline gap-x-1 gap-y-1 px-5 pb-2 pt-5 ${tools ? "pr-12" : ""}`}>{heading}{tools && <div className="absolute right-3 top-3">{tools}</div>}</header>
    <div className="min-h-0 overflow-y-auto overscroll-contain px-5" data-testid="recovery-popup-body">{children}</div>
    <footer className="flex shrink-0 flex-wrap gap-3 px-5 pb-5 pt-3">{footer}</footer>
  </section>, host)}</>;
}
