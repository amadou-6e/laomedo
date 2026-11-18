import { useEffect, useRef, useState } from "react";
import { Check, Copy } from "lucide-react";

export default function CopyAnswer({ text }: { text: string }) {
  const [state, setState] = useState<"idle" | "copied" | "failed">("idle");
  const version = useRef(0);
  useEffect(() => {
    version.current += 1;
    setState("idle");
    return () => { version.current += 1; };
  }, [text]);
  return (
    <div className="flex items-center gap-2 text-xs text-muted-foreground">
      <button
        type="button"
        aria-label="Copy answer"
        title="Copy answer"
        className="rounded p-1 hover:bg-muted hover:text-foreground focus-visible:outline focus-visible:outline-2"
        onClick={async () => {
          const current = version.current;
          try {
            await navigator.clipboard.writeText(text);
            if (current === version.current) setState("copied");
          } catch {
            if (current === version.current) setState("failed");
          }
        }}
      >
        {state === "copied" ? <Check size={14} /> : <Copy size={14} />}
      </button>
      <span role="status" aria-live="polite">
        {state === "copied" ? "Copied" : state === "failed" ? "Could not copy. Select the text to copy it." : ""}
      </span>
    </div>
  );
}
