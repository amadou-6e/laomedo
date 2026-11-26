import { useEffect, useState } from "react";
import { readSubscriptionLimits, type SubscriptionWindow } from "@/components/laomedoProviders/api";
import NativeUsage from "./NativeUsage";
import { UserMessage } from "../messages/Message";

export default function OpenCodeUsage({ connection, generation }: { connection: string; generation: number }) {
  const [text, setText] = useState<string>();
  const [windows, setWindows] = useState<SubscriptionWindow[]>([]);
  useEffect(() => {
    const controller = new AbortController();
    void readSubscriptionLimits("", connection, generation, {refresh: true, signal: controller.signal}).then(result => {
      if (controller.signal.aborted) return;
      const windows = result.snapshot?.buckets.flatMap(bucket => bucket.windows) ?? [];
      setWindows(windows);
      setText(windows.length ? (result.state === "ready" ? "" : "**Last known limits:**\n\n") + windows.map(window => {
        const name = window.kind === "monthly" ? "Monthly" : window.window_minutes === 300 ? "5-hour" : "Weekly";
        const allowance = window.used_percent === null ? "Allowance unknown" : `${Math.max(0, 100 - window.used_percent)}% remaining`;
        const reset = window.resets_at === null ? "Reset time unknown" : `Resets ${new Date(window.resets_at * 1000).toLocaleString()}`;
        return `**${name} limit:** ${allowance}\n\n${reset}`;
      }).join("\n\n") : result.reason === "busy" ? "Account is busy. Try /usage when its run finishes." : "Subscription limits are unavailable. Check the connection in Settings.");
    }).catch(() => { if (!controller.signal.aborted) setText("Could not check subscription limits. Try /usage again."); });
    return () => controller.abort();
  }, [connection, generation]);
  return <section aria-label="OpenCode usage" className="space-y-5 [&>section]:w-full [&>section]:max-w-md">
    <UserMessage text="/usage" command />
    {text ? <NativeUsage text={text} provider="OpenCode" collapsible={false} windows={windows} /> : <p role="status" className="text-xs text-muted-foreground">Checking usage...</p>}
  </section>;
}
