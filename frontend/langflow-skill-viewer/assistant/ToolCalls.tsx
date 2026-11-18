import { ChevronRight, Terminal } from "lucide-react";
import type { Lane } from "@/modals/graphAgents/models";
import { duration, time } from "@/modals/graphAgents/utils";
import { toolCall } from "./toolCall";

export default function ToolCalls({
  lanes,
  names,
}: {
  lanes: Lane[];
  names: Record<string, string>;
}) {
  return (
    <div className="min-w-0 border-y bg-muted/40" aria-label="Tool calls">
      {lanes.map((lane) => {
        const { name, input, output } = toolCall(lane, names);
        return (
          <details
            key={`${lane.thread}:${lane.id}`}
            className="group min-w-0 border-b px-3 py-2 text-[11px] last:border-b-0"
          >
            <summary className="flex cursor-pointer list-none flex-wrap items-center justify-between gap-x-4 gap-y-1 text-muted-foreground [&::-webkit-details-marker]:hidden">
              <span className="flex min-w-0 items-center gap-2">
                <Terminal size={12} className="shrink-0" />
                <span className="break-words">{name}</span>
                {lane.item?.type === "contextCompaction" && <span>{lane.status === "completed" ? "Completed" : lane.status ?? "Outcome unavailable"}</span>}
                <ChevronRight
                  size={10}
                  className="shrink-0 transition-transform group-open:rotate-90"
                />
              </span>
              <span
                className="tabular-nums"
                title={`${lane.started} → ${lane.ended ?? "running"}`}
              >
                {time(lane.started)} · {duration(lane.started, lane.ended)}
              </span>
            </summary>
            {lane.conflicting_receipts && (
              <p role="status" className="mt-2">
                Conflicting native receipts retained.
              </p>
            )}
            {lane.item?.type === "contextCompaction" && (
              <p className="mt-2 text-muted-foreground">{lane.status === "completed" ? "Context compaction completed." : `Context compaction: ${lane.status ?? "outcome unavailable"}.`}</p>
            )}
            {input != null && (
              <pre className="mt-2 max-h-56 overflow-auto whitespace-pre-wrap break-words">
                {typeof input === "string"
                  ? input
                  : JSON.stringify(input, null, 2)}
              </pre>
            )}
            {output != null && (
              <pre className="mt-2 max-h-56 overflow-auto whitespace-pre-wrap break-words">
                {typeof output === "string"
                  ? output
                  : JSON.stringify(output, null, 2)}
              </pre>
            )}
          </details>
        );
      })}
    </div>
  );
}
