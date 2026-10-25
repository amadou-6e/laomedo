import { useState } from "react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { describeNodeFailure, type ErrorContext } from "./nodeErrors";

export default function NodeErrorNotice({ message, status, context, inline = false }: {
  message?: unknown; status?: unknown; context: ErrorContext; inline?: boolean;
}) {
  const failure = describeNodeFailure(message, status, context);
  const [copied, setCopied] = useState("");
  const details = JSON.stringify(failure.diagnostics, null, 2);
  const copy = async () => {
    try { await navigator.clipboard.writeText(details); setCopied("Copied"); }
    catch { setCopied("Copy unavailable. Select the details to copy them manually."); }
  };
  const name = (context.nodeLabel || context.nodeType || "Laomedo node").slice(0, 120);
  const content = <>
      <h3 className="text-base font-semibold">{failure.title}</h3>
      <p className="text-xs text-muted-foreground">{name}{failure.diagnostics.operation ? ` / ${failure.diagnostics.operation}` : ""}</p>
      <p className="text-sm">{failure.description}</p>
      <div className="space-y-1"><h4 className="text-sm font-medium">What to do</h4><p className="text-sm">{failure.recovery}</p></div>
      <details><summary className="cursor-pointer text-sm font-medium">Technical details</summary>
        <p className="mt-2 text-xs text-muted-foreground">Only the error code and safe identifiers are included. Payloads, credentials and stack traces are omitted.</p>
        <pre className="my-2 select-text whitespace-pre-wrap break-all rounded bg-muted p-3 text-xs">{details}</pre>
        <button type="button" onClick={copy} className="rounded border px-2 py-1 text-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">Copy diagnostics</button>
        <p role="status" className="mt-1 text-xs">{copied}</p>
      </details>
  </>;
  if (inline) return <div className="space-y-3 p-1 text-foreground">{content}</div>;
  return <Popover>
    <PopoverTrigger asChild>
      <button type="button" className="nodrag nopan rounded px-1 py-0.5 text-xs font-medium text-error-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        aria-label={`Error details: ${failure.title}`} title={failure.title}>Error details</button>
    </PopoverTrigger>
    <PopoverContent side="bottom" className="nodrag nopan nowheel max-h-[min(36rem,80vh)] w-[min(28rem,calc(100vw-2rem))] space-y-3 overflow-y-auto p-4" aria-label="Node error explanation">{content}</PopoverContent>
  </Popover>;
}
