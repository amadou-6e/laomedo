import { z } from "zod";

export const connectionSchema = z.object({
  connection_id: z.string().uuid(),
  provider: z.enum(["codex", "claude", "opencode"]),
  method: z.enum(["chatgpt_plan_oauth", "claude_native", "opencode_go_key"]),
  label: z.string(),
  generation: z.number().int().positive(),
  auth_state: z.enum(["ready", "expired", "reauthorization_required", "revoked", "unavailable"]),
  lifecycle: z.enum(["connected", "disconnecting", "cleanup_required"]).default("connected"),
});
const progressSchema = z.object({
  provider: z.enum(["codex", "claude"]).optional(),
  attempt_id: z.string().uuid(),
  status: z.enum(["connecting", "verifying", "connected", "cancelled", "expired", "failed", "duplicate"]),
  connection_id: z.string().uuid().nullable(),
  code: z.string().nullable(),
});
export type ProviderConnection = z.infer<typeof connectionSchema>;
export type LoginProgress = z.infer<typeof progressSchema>;
const prefix = "/api/v1/laomedo/provider-connections";
const disconnectInfoSchema = z.object({ connection_id: z.string().uuid(), generation: z.number().int().positive(), active_runs: z.number().int().nonnegative(), revision: z.number().int().nonnegative() });
const disconnectProgressSchema = z.object({ connection_id: z.string().uuid(), status: z.enum(["disconnecting", "cleanup_required", "removed"]) });
export type DisconnectInfo = z.infer<typeof disconnectInfoSchema>;

export class ProviderFailure extends Error {
  constructor(public code: string) { super(code); }
}

async function request(path = "", method = "GET", body?: unknown) {
  const response = await fetch(prefix + path, {
    method, credentials: "same-origin", cache: "no-store",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(15000),
  });
  const value = await response.json().catch(() => null);
  if (!response.ok) {
    const code = value?.detail?.code;
    throw new ProviderFailure(["provider_login_expired", "provider_login_in_progress", "provider_confirmation_changed", "provider_connection_busy"].includes(code) ? code : "provider_connections_unavailable");
  }
  return value;
}

export async function listConnections(): Promise<ProviderConnection[]> {
  return z.object({ connections: z.array(connectionSchema) }).parse(await request()).connections;
}

export async function beginLogin(connectionId?: string, provider: "codex" | "claude" = "codex") {
  const result = z.object({ progress: progressSchema, authorization_url: z.string().url().nullable() }).parse(
    await request("/attempts", "POST", { provider, ...(connectionId ? { connection_id: connectionId } : {}) }),
  );
  if (provider === "claude") {
    if (result.authorization_url) validateClaudeUrl(result.authorization_url);
    return result;
  }
  if (!result.authorization_url) throw new Error("provider_connections_unavailable");
  const url = new URL(result.authorization_url);
  if (url.origin !== "https://auth.openai.com" || url.pathname !== "/api/accounts/authorize" || url.username || url.password)
    throw new Error("provider_connections_unavailable");
  return result;
}

function validateClaudeUrl(value: string) {
  const url = new URL(value);
  if (!["https://claude.ai", "https://platform.claude.com"].includes(url.origin) || url.pathname !== "/oauth/authorize" || url.username || url.password)
    throw new Error("provider_connections_unavailable");
}

export async function readClaudeAttempt(attemptId: string) {
  const result = z.object({ progress: progressSchema, authorization_url: z.string().url().nullable() }).parse(await request(`/claude/attempts/${encodeURIComponent(attemptId)}`));
  if (result.authorization_url) validateClaudeUrl(result.authorization_url);
  return result;
}

export async function submitClaudeCode(attemptId: string, code: string) {
  return progressSchema.parse(await request(`/claude/attempts/${encodeURIComponent(attemptId)}/code`, "POST", { code }));
}

export async function readProgress(attemptId: string): Promise<LoginProgress> {
  return progressSchema.parse(await request(`/attempts/${encodeURIComponent(attemptId)}`));
}

export async function cancelLogin(attemptId: string): Promise<LoginProgress> {
  return progressSchema.parse(await request(`/attempts/${encodeURIComponent(attemptId)}/cancel`, "POST", {}));
}

export async function inspectDisconnect(connectionId: string) {
  return disconnectInfoSchema.parse(await request(`/${encodeURIComponent(connectionId)}/disconnect`));
}

export async function disconnect(info: DisconnectInfo) {
  return disconnectProgressSchema.parse(await request(`/${encodeURIComponent(info.connection_id)}/disconnect`, "POST", { generation: info.generation, revision: info.revision }));
}

export async function retryCleanup(connectionId: string) {
  return disconnectProgressSchema.parse(await request(`/${encodeURIComponent(connectionId)}/cleanup`, "POST", {}));
}

const graphPreferencesSchema = z.object({ codex: z.string().uuid().nullable(), claude: z.string().uuid().nullable().default(null), opencode: z.string().uuid().nullable().default(null) });
export async function readGraphPreferences(flowId: string) {
  return graphPreferencesSchema.parse(await request(`/graphs/${encodeURIComponent(flowId)}`));
}
export async function saveGraphPreferences(flowId: string, codex: string | null, others?: { claude: string | null; opencode: string | null }) {
  return graphPreferencesSchema.parse(await request(`/graphs/${encodeURIComponent(flowId)}`, "PUT", { codex, ...others }));
}

export async function saveGoConnection(key: string, label: string) {
  return z.object({ connection: connectionSchema, duplicate: z.boolean() }).parse(await request("/opencode-go", "POST", { key, label }));
}
