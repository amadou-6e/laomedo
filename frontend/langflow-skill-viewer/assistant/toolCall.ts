import type { Lane } from "@/modals/graphAgents/models";

export function toolCall(lane: Lane, names: Record<string, string>) {
  const item = lane.item ?? {};
  const candidate = String(item.toolName ?? item.tool ?? item.name ?? "");
  return {
    name: names[candidate] ??
      (candidate && !/^external_[a-f0-9]+$/i.test(candidate)
        ? candidate
        : item.type === "commandExecution" ? "Command" : "Tool call"),
    input: item.arguments ?? item.input ?? item.command,
    output: item.output ?? item.result ?? item.aggregatedOutput,
  };
}
