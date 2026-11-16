import { z } from "zod";

export const connectionSchema = z.object({
  connection_id: z.string().uuid(),
  provider: z.literal("codex"),
  method: z.literal("chatgpt_plan_oauth"),
  label: z.string(),
  generation: z.number().int().positive(),
  auth_state: z.enum(["ready", "expired", "reauthorization_required", "revoked", "unavailable"]),
});
const progressSchema = z.object({
  attempt_id: z.string().uuid(),
  status: z.enum(["connecting", "verifying", "connected", "cancelled", "expired", "failed", "duplicate"]),
  connection_id: z.string().uuid().nullable(),
  code: z.string().nullable(),
});
export type ProviderConnection = z.infer<typeof connectionSchema>;
export type LoginProgress = z.infer<typeof progressSchema>;
const prefix = "/api/v1/laomedo/provider-connections";

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
    throw new ProviderFailure(["provider_login_expired", "provider_login_in_progress"].includes(code) ? code : "provider_connections_unavailable");
  }
  return value;
}

export async function listConnections(): Promise<ProviderConnection[]> {
  return z.object({ connections: z.array(connectionSchema) }).parse(await request()).connections;
}

export async function beginLogin(connectionId?: string) {
  const result = z.object({ progress: progressSchema, authorization_url: z.string().url() }).parse(
    await request("/attempts", "POST", { provider: "codex", ...(connectionId ? { connection_id: connectionId } : {}) }),
  );
  const url = new URL(result.authorization_url);
  if (url.origin !== "https://auth.openai.com" || url.pathname !== "/api/accounts/authorize" || url.username || url.password)
    throw new Error("provider_connections_unavailable");
  return result;
}

export async function readProgress(attemptId: string): Promise<LoginProgress> {
  return progressSchema.parse(await request(`/attempts/${encodeURIComponent(attemptId)}`));
}

export async function cancelLogin(attemptId: string): Promise<LoginProgress> {
  return progressSchema.parse(await request(`/attempts/${encodeURIComponent(attemptId)}/cancel`, "POST", {}));
}
