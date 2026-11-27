import type { Projection } from "@/modals/graphAgents/models";

export type SavedConnection = { connection_id: string; provider: string; method?: string; label: string; generation: number; lifecycle: string; auth_state: string };

export type Conversation = {
  connection_id?: string | null;
  connection_generation?: number | null;
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
  initial_native_command?: "status" | null;
  native_action_id?: string | null;
  model?: string | null;
  effort?: string | null;
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
export type PendingSubmission = {
  initial_native_command?: "status";
  id: string;
  text: string;
  model?: string;
  effort?: string;
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
export type GraphAction = {
  id: string;
  message_id: string;
  can_decide?: boolean;
  workflow_id: string;
  name: string;
  kind: "edit" | "run";
  category?: "rename" | "edit" | "run";
  summary?: string;
  new_name?: string | null;
  digest: string;
  error_code?: string | null;
  preview: string[];
  revision: string;
  state: string;
  expires_at: number;
  run_id: string | null;
};
export type ConversationDetail = {
  native_actions?: NativeAction[];
  permissions?: ("rename" | "edit" | "run")[];
  actions?: GraphAction[];
  conversation: Conversation;
  messages: Message[];
  drafts: DraftReceipt[];
  next_cursor: number | null;
  observation_error?: string;
};
export type NativeAction = {
  id: string;
  message_id: string;
  name: string;
  arguments: string;
  digest: string;
  state: string;
  may_use_model: boolean;
  can_decide: boolean;
  result_message_id: string | null;
};
export type NativeCommandCatalog = {
  state: "available" | "unavailable";
  revision?: string;
  reason?: string;
  commands: { name: string; kind?: "command" | "skill"; description: string; input_hint?: string | null; executable: boolean; accepts_arguments: boolean; reason?: string | null }[];
};
export type ActivityPage = {
  tool_names?: Record<string, string>;
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
