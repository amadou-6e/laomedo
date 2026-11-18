import { messageText } from "@/modals/graphAgents/utils";
import { assistantRequest } from "./api";
import type { ActivityPage, ConversationDetail, Message } from "./models";

export async function conversationTranscript(
  conversation: string,
  signal: AbortSignal,
): Promise<{ text: string; filename: string }> {
  const messages = new Map<string, Message>();
  const visited = new Set<number>();
  let cursor: number | null = 0;
  let title = "Conversation";
  while (cursor !== null) {
    if (visited.has(cursor)) throw new Error("Repeated history cursor");
    visited.add(cursor);
    const page: ConversationDetail = await assistantRequest(
      `/conversations/${encodeURIComponent(conversation)}?cursor=${cursor}`,
      undefined,
      signal,
    );
    if (cursor === 0) title = page.conversation.title;
    for (const message of page.messages)
      if (!messages.has(message.id)) messages.set(message.id, message);
    cursor = page.next_cursor;
  }
  const blocks = [
    `# ${title.replace(/[\r\n]+/g, " ")}`,
    "Retained conversation snapshot. Includes user and assistant text; tool payloads are excluded.",
  ];
  for (const message of [...messages.values()].sort((a, b) => a.created_at - b.created_at)) {
    blocks.push("## You", message.text);
    const activity = await assistantRequest<ActivityPage>(
      `/conversations/${encodeURIComponent(conversation)}/activity?attempt=${encodeURIComponent(message.attempt_id)}&after=0`,
      undefined,
      signal,
    );
    const answers = (activity.projection?.items ?? [])
      .filter((lane) => lane.item?.type !== "userMessage")
      .map((lane) => messageText(lane.item ?? {}, "codex"))
      .filter((text): text is string => text !== null);
    if (!answers.length && message.response) answers.push(message.response);
    if (answers.length) blocks.push("## Assistant", answers.join("\n\n"));
    if (!activity.available || activity.complete === false)
      blocks.push("_Some activity is unavailable or was not retained; this answer may be partial._");
    if (message.state !== "completed")
      blocks.push(`_Response state at export: ${message.state}._`);
  }
  return {
    text: blocks.join("\n\n") + "\n",
    filename: (title.replace(/[^a-zA-Z0-9_-]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 80) || "conversation") + ".md",
  };
}

export function downloadTranscript(text: string, filename: string): void {
  const url = URL.createObjectURL(new Blob([text], { type: "text/markdown;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
