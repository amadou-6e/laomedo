import { useState } from "react";
import { nativeStatus } from "./statusFields";

export default function NativeStatus({ text, conversation }: { text: string; conversation: string }) {
  const [closed, setClosed] = useState(false);
  const { fields, limits } = nativeStatus(text);
  const recognized = ["session", "context window", "model", "approval", "sandbox"].some((key) => fields.has(key)) || limits.length > 0;
  if (closed) return <button type="button" className="text-xs text-muted-foreground hover:text-foreground" onClick={() => setClosed(false)}>Show status</button>;
  const rows = [
    ["Chat", conversation],
    ["Thread", fields.get("session") ?? "Unavailable"],
    ["Context", fields.get("context window") ?? "Unavailable"],
    ["Model", fields.get("model")],
    ["Approval", fields.get("approval")],
    ["Sandbox", fields.get("sandbox")],
  ];
  return (
    <section aria-label="Codex status" className="rounded-xl border bg-muted/50 px-3 py-2 text-[11px] text-muted-foreground">
      <div className="mb-3 flex items-center justify-between">
        <span className="text-xs">Status</span>
        <button type="button" className="hover:text-foreground" onClick={() => setClosed(true)} aria-label="Close status">Close</button>
      </div>
      <dl className="space-y-2 font-mono">
        {rows.filter(([, value]) => value).map(([label, value]) => (
          <div key={label} className="flex gap-3">
            <dt className="w-16 shrink-0">{label}:</dt>
            <dd className="min-w-0 break-all">{value}</dd>
          </div>
        ))}
        {limits.map((limit) => (
          <div key={limit.name} className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <dt className="w-16 shrink-0">{limit.name}:</dt>
            <dd className="flex min-w-0 flex-1 flex-wrap items-center gap-3">
              {limit.remaining !== null && <span role="meter" aria-label={limit.name} aria-valuemin={0} aria-valuemax={100} aria-valuenow={limit.remaining} aria-valuetext={limit.value} className="h-2 w-32 overflow-hidden bg-foreground/10"><span className="block h-full bg-foreground/40" style={{ width: `${limit.remaining}%` }} /></span>}
              <span>{limit.value}</span>
            </dd>
          </div>
        ))}
      </dl>
      {!recognized && <pre className="mt-2 whitespace-pre-wrap break-words font-mono">{text}</pre>}
    </section>
  );
}
