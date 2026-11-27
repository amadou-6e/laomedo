import type { SubscriptionWindow } from "@/components/laomedoProviders/api";
import { useState } from "react";
import { MessageMarkdown } from "@/modals/graphAgents/components";

export default function NativeUsage({ text, provider = "Claude", collapsible = true, windows }: { text: string; provider?: string; collapsible?: boolean; windows?: SubscriptionWindow[] }) {
  const [closed, setClosed] = useState(false);
  if (closed) return <button type="button" className="text-xs text-muted-foreground hover:text-foreground" onClick={() => setClosed(false)}>Show limits</button>;
  return (
    <section aria-label={`${provider} usage limits`} className="rounded-xl border bg-muted/50 px-3 py-2 text-[11px] text-muted-foreground">
      <div className="mb-3 flex items-center justify-between">
        <span className="text-xs">Limits</span>
        {collapsible && <button type="button" className="hover:text-foreground" onClick={() => setClosed(true)} aria-label="Close limits">Close</button>}
      </div>
      {windows?.length ? <div className="space-y-4 font-mono">
        {text.startsWith("**Last known limits:") && <p>Last known limits</p>}
        {windows.map(window => {
          const label = window.kind === "monthly" ? "Monthly limit" : window.window_minutes === 300 ? "5-hour limit" : "Weekly limit";
          const remaining = window.used_percent === null ? null : Math.max(0, Math.min(100, 100 - window.used_percent));
          return <div key={window.kind} className="space-y-1.5">
            <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1"><span>{label}</span><span>{remaining === null ? "Allowance unknown" : `${remaining}% remaining`}</span></div>
            {remaining !== null && <div role="meter" aria-label={`${label} remaining`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={remaining} className="h-2 overflow-hidden rounded-sm bg-foreground/10"><div className="h-full bg-foreground/40" style={{width: `${remaining}%`}} /></div>}
            <p className="text-[10px] text-muted-foreground/80">{window.resets_at === null ? "Reset time unknown" : `Resets ${new Date(window.resets_at * 1000).toLocaleString()}`}</p>
          </div>;
        })}
      </div> : <div className="font-mono [&_p]:text-[11px] [&_p]:text-muted-foreground [&_strong]:font-normal [&_hr]:hidden">
        <MessageMarkdown text={text.replace(/^#{1,6}\s+Limits\s*\n/i, "")} allowLinks={false} />
      </div>}

    </section>
  );
}
