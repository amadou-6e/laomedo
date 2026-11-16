import type { Projection } from "@/modals/graphAgents/models";

export type Conversation = {
  id: string;
  title: string;
  provider: string;
  model: string;
  effort: string;
  state: string;
  active_message_id: string | null;
  error_code: string | null;
  run_id: string | null;
  thread_id: string | null;
  updated_at: number;
  linked_conversation_id: string | null;
};
export type Message = {
  id: string;
  client_message_id: string;
  attempt_id: string;
  native_attempt_id: string | null;
  text: string;
  state: string;
  response: string | null;
  error_code: string | null;
  run_id: string | null;
  created_at: number;
  stop_requested: boolean;
};
export type DraftReceipt = {
  id: string;
  message_id: string;
  attempt_id: string;
  draft_key: string;
  workflow_id: string;
  name: string;
  revision: string;
  diagnostics: string[];
  created_at: number;
};
export type ConversationIndex = {
  conversations: Conversation[];
  next_cursor: number | null;
};
export type ConversationDetail = {
  conversation: Conversation;
  messages: Message[];
  drafts: DraftReceipt[];
  next_cursor: number | null;
  observation_error?: string;
};
export type ActivityPage = {
  available: boolean;
  reason: string | null;
  projection: Projection | null;
  projection_revision?: number;
  thread_id?: string | null;
  closed: boolean;
  complete: boolean | null;
};
export type Models = {
  provider: string;
  models: { id: string; efforts: string[] }[];
};

export function stateLabel(value: string): string {
  if (["starting", "reserved"].includes(value)) return "starting";
  if (value === "running") return "responding";
  if (value === "stopping") return "stopping";
  if (["unknown", "reconciling"].includes(value)) return "reconciling";
  if (value === "attention") return "Cannot safely continue";
  if (value === "cancelled") return "Response stopped";
  if (["failed", "interrupted"].includes(value)) return "Response failed";
  return "Ready";
}
