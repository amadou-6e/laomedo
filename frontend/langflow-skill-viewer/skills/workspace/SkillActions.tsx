import { useEffect, useRef, type ReactNode } from "react";

const dismissedEscapes = new WeakSet<Event>();

export function dismissSkillActions(event: KeyboardEvent): boolean {
  // React and the dialog's native Escape listener can see the same event in either order.
  if (dismissedEscapes.has(event)) return true;
  const target = event.target instanceof Element ? event.target : document.activeElement;
  const open = target?.closest<HTMLDetailsElement>('details[data-skill-actions][open]');
  if (!open) return false;
  dismissedEscapes.add(event);
  open.open = false;
  open.querySelector('summary')?.focus();
  return true;
}

/** Native disclosure with menu dismissal and focus return, without menu-role arrow-key semantics. */
export default function SkillActions({ label, children }: { label: string; children: ReactNode }) {
  const disclosure = useRef<HTMLDetailsElement>(null);
  const trigger = useRef<HTMLElement>(null);
  useEffect(() => {
    const outside = (event: PointerEvent) => {
      if (disclosure.current && !disclosure.current.contains(event.target as Node)) disclosure.current.open = false;
    };
    document.addEventListener("pointerdown", outside, true);
    return () => document.removeEventListener("pointerdown", outside, true);
  }, []);
  return <details data-skill-actions ref={disclosure} className="relative mr-1"
    onBlur={(event) => { if (!event.currentTarget.contains(event.relatedTarget as Node)) event.currentTarget.open = false; }}
    onKeyDown={(event) => {
      if (event.key !== "Escape" || !dismissSkillActions(event.nativeEvent)) return;
      event.preventDefault(); event.stopPropagation();
    }}>
    <summary ref={trigger} aria-label={label} className="flex h-6 w-7 cursor-pointer list-none items-center justify-center rounded text-lg leading-none hover:bg-muted [&::-webkit-details-marker]:hidden">{'\u22ef'}</summary>
    <div className="absolute left-0 top-7 z-30 w-max min-w-44 max-w-[260px] rounded border bg-background p-1 text-foreground shadow-md"
      onClick={(event) => {
        if (!(event.target as HTMLElement).closest('button')) return;
        if (disclosure.current) disclosure.current.open = false;
        // A hide-navigation action moves focus to the persistent separator instead.
        // Check trigger visibility after the hide action commits its queued layout update.
        queueMicrotask(() => { if (trigger.current?.getClientRects().length) trigger.current.focus(); });
      }}>{children}</div>
  </details>;
}
