import { useEffect, useRef, type ReactNode } from "react";

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
  return <details ref={disclosure} className="relative mr-1"
    onBlur={(event) => { if (!event.currentTarget.contains(event.relatedTarget as Node)) event.currentTarget.open = false; }}
    onKeyDown={(event) => {
      if (event.key !== "Escape" || !event.currentTarget.open) return;
      event.preventDefault(); event.stopPropagation(); event.currentTarget.open = false; trigger.current?.focus();
    }}>
    <summary ref={trigger} aria-label={label} className="flex h-6 w-7 cursor-pointer list-none items-center justify-center rounded text-lg leading-none hover:bg-muted [&::-webkit-details-marker]:hidden">{'\u22ef'}</summary>
    <div className="absolute right-0 top-7 z-30 w-max min-w-44 rounded border bg-background p-1 text-foreground shadow-md"
      onClick={(event) => {
        if (!(event.target as HTMLElement).closest('button')) return;
        if (disclosure.current) disclosure.current.open = false;
        // A hide-navigation action moves focus to the persistent separator instead.
        if (trigger.current?.getClientRects().length) trigger.current.focus();
      }}>{children}</div>
  </details>;
}
