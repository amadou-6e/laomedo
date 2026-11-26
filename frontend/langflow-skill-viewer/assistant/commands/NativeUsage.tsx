import { useState } from "react";
import { MessageMarkdown } from "@/modals/graphAgents/components";

export default function NativeUsage({ text, provider = "Claude", collapsible = true }: { text: string; provider?: string; collapsible?: boolean }) {
  const [closed, setClosed] = useState(false);
  if (closed) return <button type="button" className="text-xs text-muted-foreground hover:text-foreground" onClick={() => setClosed(false)}>Show limits</button>;
  return (
    <section aria-label={`${provider} usage limits`} className="rounded-xl border bg-muted/50 px-3 py-2 text-[11px] text-muted-foreground">
      <div className="mb-3 flex items-center justify-between">
        <span className="text-xs">Limits</span>
        {collapsible && <button type="button" className="hover:text-foreground" onClick={() => setClosed(true)} aria-label="Close limits">Close</button>}
      </div>
      <div className="font-mono [&_p]:text-[11px] [&_p]:text-muted-foreground [&_strong]:font-normal [&_hr]:hidden">
        <MessageMarkdown text={text.replace(/^#{1,6}\s+Limits\s*\n/i, "")} allowLinks={false} />
      </div>
    </section>
  );
}
