import type { Lane } from "@/modals/graphAgents/models";
import { duration, time } from "@/modals/graphAgents/utils";

export default function ToolCalls({ lanes }: { lanes: Lane[] }) {
  return (
    <div
      className="overflow-hidden rounded-xl border bg-muted/20"
      aria-label="Tool calls"
    >
      {lanes.map((lane) => {
        const item = lane.item ?? {};
        const candidate = String(item.toolName ?? item.tool ?? item.name ?? "");
        const name =
          candidate && !/^external_[a-f0-9]+$/i.test(candidate)
            ? candidate
            : item.type === "commandExecution"
              ? "Command"
              : "Laomedo tool";
        const output = item.output ?? item.result ?? item.aggregatedOutput;
        const input = item.arguments ?? item.input ?? item.command;
        return (
          <div
            key={`${lane.thread}:${lane.id}`}
            className="space-y-2 border-b px-3 py-3 last:border-b-0"
          >
            <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
              <span className="font-medium">{name}</span>
              <span
                className="tabular-nums text-muted-foreground"
                title={`${lane.started} → ${lane.ended ?? "running"}`}
              >
                {time(lane.started)} · {duration(lane.started, lane.ended)}
              </span>
            </div>
            {lane.conflicting_receipts && (
              <p role="status" className="text-xs">
                Conflicting native receipts retained.
              </p>
            )}
            {(input != null || output != null) && (
              <details className="text-xs text-muted-foreground">
                <summary className="cursor-pointer">Details</summary>
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
            )}
          </div>
        );
      })}
    </div>
  );
}
