import { messageText } from "@/modals/graphAgents/utils";
import type { ActivityPage, DraftReceipt, GraphAction, Message, NativeAction } from "./models";
import { toolCall } from "./toolCall";

export function isNativeControlCommand(provider: string, name: string): boolean {
  return (provider === "codex" ? ["status", "mcp", "skills"] : provider === "claude" ? ["usage", "context", "mcp"] : []).includes(name);
}

export function hasNativeControlResult(message: Message, provider = "codex"): boolean {
  return Boolean((message.native_action_id || provider === "codex" && message.initial_native_command === "status") && message.state === "completed" && message.response && isNativeControlCommand(provider, message.text.slice(1)) && message.text.startsWith("/"));
}

export function hasNativeCommandOutcome(message: Message, provider = "codex"): boolean {
  return hasNativeControlResult(message, provider) || Boolean(message.native_action_id && message.state === "completed" && message.text === "/compact");
}

function fenced(value: unknown): string {
  const text = typeof value === "string" ? value : JSON.stringify(value, null, 2);
  const fence = "`".repeat(Math.max(3, ...Array.from(text.matchAll(/`+/g), (match) => match[0].length + 1)));
  return `${fence}\n${text}\n${fence}`;
}

export function responseTranscript(
  page: ActivityPage | undefined,
  message: Message,
  receipts: DraftReceipt[],
  actions: GraphAction[],
  nativeActions: NativeAction[] = [],
  provider: string = "codex",
): string {
  const blocks: string[] = [];
  let hasAnswer = false;
  for (const lane of hasNativeControlResult(message, provider) ? [] : page?.projection?.items ?? []) {
    if (lane.item?.type === "userMessage") continue;
    const text = messageText(lane.item ?? {}, provider);
    if (text !== null) {
      hasAnswer = true;
      blocks.push(text);
    } else {
      const call = toolCall(lane, page?.tool_names ?? {});
      blocks.push(`### ${call.name}`);
      if (call.input != null) blocks.push("Input", fenced(call.input));
      if (call.output != null) blocks.push("Output", fenced(call.output));
      if (lane.status) blocks.push(`Status: ${lane.status}`);
      if (lane.conflicting_receipts) blocks.push("Conflicting native receipts retained.");
    }
  }
  if (!hasAnswer && message.response) blocks.push(message.response);
  if (hasNativeCommandOutcome(message, provider) && message.text === "/compact" && !message.response)
    blocks.push("Native command: /compact", "Outcome: completed");
  for (const action of actions) {
    const category = action.category ?? action.kind;
    const description = category === "rename"
      ? `Rename workflow ${JSON.stringify(action.name)} to ${JSON.stringify(action.new_name)}`
      : `${category === "run" ? "Run" : "Edit"} workflow ${JSON.stringify(action.name)}`;
    const state = action.state === "pending" && action.expires_at * 1000 <= Date.now() ? "expired" : action.state;
    blocks.push(`### ${description}`, ...(action.summary ? [action.summary] : []),
      ...action.preview, `Outcome: ${state}`);
  }
  for (const receipt of receipts) {
    blocks.push(`### Saved draft: ${receipt.name}`, `Workflow: ${receipt.workflow_id}`,
      ...receipt.diagnostics, "Saved without running or publishing.");
  }
  for (const action of nativeActions) {
    blocks.push(`Native command: /${action.name}${action.arguments ? " " + action.arguments : ""}`, `Outcome: ${provider === "claude" && isNativeControlCommand(provider, action.name) && action.state === "completed" ? "output received" : action.state}`);
  }
  if (message.error_code) blocks.push(`Response error: ${message.error_code}`);
  if (!hasNativeCommandOutcome(message, provider) && (!page || !page.available || page.complete === false))
    blocks.push("Some activity is unavailable or was not retained; this copy may be partial.");
  if (message.state !== "completed") blocks.push(`Response state: ${message.state}. Copied activity is a snapshot.`);
  return blocks.join("\n\n");
}
