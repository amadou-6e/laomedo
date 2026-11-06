import { useEffect, useRef, useState } from "react";
export default function CopyIcon({ text, label = "Copy error" }: { text: string; label?: string }) {
  const [state, setState] = useState<"idle"|"pending"|"copied"|"failed">("idle");
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  useEffect(() => () => clearTimeout(timer.current), []);
  const message = state === "copied" ? "Copied" : state === "failed" ? "Copy unavailable. Select the text to copy it manually." : label;
  const copy = async () => {
    if (state === "pending") return;
    clearTimeout(timer.current); setState("pending");
    try { await navigator.clipboard.writeText(text); setState("copied"); timer.current = setTimeout(() => setState("idle"), 2000); }
    catch { setState("failed"); }
  };
  return <><button type="button" title={message} aria-label={message} disabled={state === "pending"} onClick={() => void copy()}
    className="flex h-8 w-8 items-center justify-center rounded text-muted-foreground hover:bg-muted hover:text-foreground focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 disabled:opacity-50">
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
      {state === "copied" ? <path d="m5 12 4 4L19 6"/> : state === "failed" ? <><circle cx="12" cy="12" r="9"/><path d="M12 7v6m0 3v1"/></> : <><rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V4H4v12h4"/></>}
    </svg>
  </button><span role={state === "copied" || state === "failed" ? "status" : undefined} aria-live="polite" className="sr-only">{state === "copied" || state === "failed" ? message : ""}</span></>;
}
