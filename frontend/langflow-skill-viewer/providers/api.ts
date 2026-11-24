import { z } from "zod";

export const connectionSchema = z.object({
  connection_id: z.string().uuid(),
  provider: z.enum(["codex", "claude", "opencode"]),
  method: z.enum(["chatgpt_plan_oauth", "claude_native", "opencode_go_key"]),
  label: z.string(),
  generation: z.number().int().positive(),
  auth_state: z.enum([
    "ready",
    "expired",
    "reauthorization_required",
    "revoked",
    "unavailable",
  ]),
  lifecycle: z
    .enum(["connected", "disconnecting", "cleanup_required"])
    .default("connected"),
});
const progressSchema = z.object({
  provider: z.enum(["codex", "claude"]).optional(),
  attempt_id: z.string().uuid(),
  status: z.enum([
    "connecting",
    "verifying",
    "awaiting_confirmation",
    "connected",
    "cancelled",
    "expired",
    "failed",
    "duplicate",
  ]),
  connection_id: z.string().uuid().nullable(),
  code: z.string().nullable(),
});
export type ProviderConnection = z.infer<typeof connectionSchema>;
export type LoginProgress = z.infer<typeof progressSchema>;
const prefix = "/api/v1/laomedo/provider-connections";
const disconnectInfoSchema = z.object({
  connection_id: z.string().uuid(),
  generation: z.number().int().positive(),
  active_runs: z.number().int().nonnegative(),
  revision: z.number().int().nonnegative(),
});
const disconnectProgressSchema = z.object({
  connection_id: z.string().uuid(),
  status: z.enum(["disconnecting", "cleanup_required", "removed"]),
});
export type DisconnectInfo = z.infer<typeof disconnectInfoSchema>;

export class ProviderFailure extends Error {
  constructor(public code: string) { super(code); Object.setPrototypeOf(this, new.target.prototype); }
}

async function request(
  path = "",
  method = "GET",
  body?: unknown,
  options?: { signal?: AbortSignal; timeoutMs?: number },
) {
  const response = await fetch(prefix + path, {
    method,
    credentials: "same-origin",
    cache: "no-store",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: options?.signal
      ? AbortSignal.any([
          options.signal,
          AbortSignal.timeout(options.timeoutMs ?? 15000),
        ])
      : AbortSignal.timeout(options?.timeoutMs ?? 15000),
  });
  const value = await response.json().catch(() => null);
  if (!response.ok) {
    const code = value?.detail?.code;
    throw new ProviderFailure(["provider_login_expired", "provider_login_in_progress", "provider_confirmation_changed", "provider_connection_busy", "provider_session_required", "provider_connection_unavailable", "provider_connection_changed", "provider_connection_disconnecting", "provider_connections_unavailable", "provider_save_unconfirmed", "provider_connection_limit", "provider_account_mismatch", "provider_request_refused"].includes(code) ? code : "provider_connections_unavailable");
  }
  return value;
}

export async function listConnections(): Promise<ProviderConnection[]> {
  return z
    .object({ connections: z.array(connectionSchema) })
    .parse(await request()).connections;
}

export async function beginLogin(
  connectionId?: string,
  provider: "codex" | "claude" = "codex",
) {
  const result = z
    .object({
      progress: progressSchema,
      authorization_url: z.string().url().nullable(),
      user_code: z.string().min(4).max(32).nullable().optional(),
    })
    .parse(
      await request("/attempts", "POST", {
        provider,
        ...(connectionId ? { connection_id: connectionId } : {}),
      }),
    );
  if (provider === "claude") {
    if (result.authorization_url) validateClaudeUrl(result.authorization_url);
    return result;
  }
  if (result.authorization_url && result.authorization_url !== "https://auth.openai.com/codex/device")
    throw new Error("provider_connections_unavailable");
  return result;
}

function validateClaudeUrl(value: string) {
  const url = new URL(value);
  const allowed = [
    "https://claude.ai/oauth/authorize",
    "https://platform.claude.com/oauth/authorize",
    "https://claude.com/cai/oauth/authorize",
  ];
  if (
    !allowed.includes(url.origin + url.pathname) ||
    url.username ||
    url.password ||
    url.hash
  )
    throw new Error("provider_connections_unavailable");
}

export async function readClaudeAttempt(attemptId: string) {
  const result = z
    .object({
      progress: progressSchema,
      authorization_url: z.string().url().nullable(),
    })
    .parse(await request(`/claude/attempts/${encodeURIComponent(attemptId)}`));
  if (result.authorization_url) validateClaudeUrl(result.authorization_url);
  return result;
}

export async function submitClaudeCode(attemptId: string, code: string) {
  return progressSchema.parse(
    await request(
      `/claude/attempts/${encodeURIComponent(attemptId)}/code`,
      "POST",
      { code },
    ),
  );
}

export async function readProgress(attemptId: string): Promise<LoginProgress> {
  return progressSchema.parse(
    await request(`/attempts/${encodeURIComponent(attemptId)}`),
  );
}

export async function cancelLogin(attemptId: string): Promise<LoginProgress> {
  return progressSchema.parse(
    await request(
      `/attempts/${encodeURIComponent(attemptId)}/cancel`,
      "POST",
      {},
    ),
  );
}

export async function inspectDisconnect(connectionId: string) {
  return disconnectInfoSchema.parse(
    await request(`/${encodeURIComponent(connectionId)}/disconnect`),
  );
}

export async function disconnect(info: DisconnectInfo) {
  return disconnectProgressSchema.parse(
    await request(
      `/${encodeURIComponent(info.connection_id)}/disconnect`,
      "POST",
      { generation: info.generation, revision: info.revision },
    ),
  );
}

export async function retryCleanup(connectionId: string) {
  return disconnectProgressSchema.parse(
    await request(`/${encodeURIComponent(connectionId)}/cleanup`, "POST", {}),
  );
}

const graphPreferencesSchema = z.object({
  codex: z.string().uuid().nullable(),
  claude: z.string().uuid().nullable().default(null),
  opencode: z.string().uuid().nullable().default(null),
});
export async function readGraphPreferences(flowId: string) {
  return graphPreferencesSchema.parse(
    await request(`/graphs/${encodeURIComponent(flowId)}`),
  );
}
export async function saveGraphPreferences(
  flowId: string,
  codex: string | null,
  others?: { claude: string | null; opencode: string | null },
) {
  return graphPreferencesSchema.parse(
    await request(`/graphs/${encodeURIComponent(flowId)}`, "PUT", {
      codex,
      ...others,
    }),
  );
}

export async function saveGoConnection(key: string, label: string) {
  return z
    .object({ connection: connectionSchema, duplicate: z.boolean() })
    .parse(await request("/opencode-go", "POST", { key, label }));
}

const subscriptionWindowSchema = z.object({
  kind: z.enum(["primary", "secondary"]),
  used_percent: z.number().finite().nonnegative().nullable(),
  window_minutes: z.number().int().positive().nullable(),
  resets_at: z.number().int().positive().max(253402300799).nullable(),
});
const subscriptionObservationSchema = z.object({
  connection_id: z.string().uuid(),
  generation: z.number().int().positive(),
  state: z.enum(["not_checked", "ready", "stale", "unavailable"]),
  reason: z
    .enum(["unsupported", "refresh_failed", "account_unavailable", "busy"])
    .nullable(),
  observed_at: z.number().finite().nullable(),
  stale_after: z.number().finite().nullable(),
  snapshot: z
    .object({
      submitted_turns: z.literal(0),
      buckets: z
        .array(
          z.object({
            limit_id: z.string().min(1).max(128),
            label: z.string().max(128).nullable(),
            plan: z.string().max(64).nullable(),
            windows: z.array(subscriptionWindowSchema).max(2),
            credits: z
              .object({
                has_credits: z.boolean().nullable(),
                unlimited: z.boolean().nullable(),
                balance: z.string().max(64).nullable(),
              })
              .nullable(),
          }),
        )
        .max(32),
    })
    .nullable(),
});
export type SubscriptionObservation = z.infer<
  typeof subscriptionObservationSchema
>;
export type SubscriptionWindow = z.infer<typeof subscriptionWindowSchema>;

export async function readSubscriptionLimits(
  flowId: string,
  connectionId: string,
  generation: number,
  options: { refresh?: boolean; signal?: AbortSignal } = {},
): Promise<SubscriptionObservation> {
  const path = `/graphs/${encodeURIComponent(flowId)}/limits/${encodeURIComponent(connectionId)}`;
  const result = subscriptionObservationSchema.parse(
    await request(
      options.refresh ? path : `${path}?generation=${generation}`,
      options.refresh ? "POST" : "GET",
      options.refresh ? { generation } : undefined,
      { signal: options.signal, timeoutMs: 180000 },
    ),
  );
  if (result.connection_id !== connectionId || result.generation !== generation)
    throw new ProviderFailure("provider_connection_changed");
  return result;
}


export async function readCodexAttempt(attemptId: string) {
  const result = z.object({
    progress: progressSchema,
    authorization_url: z.literal("https://auth.openai.com/codex/device").nullable(),
    user_code: z.string().min(4).max(32).nullable(),
    replacement_account: z.object({email: z.string(), account_id: z.string(), plan_type: z.string()}).nullable(),
  }).parse(await request(`/codex/attempts/${encodeURIComponent(attemptId)}`));
  return result;
}

export async function confirmCodexReplacement(attemptId: string) {
  return progressSchema.parse(await request(`/codex/attempts/${encodeURIComponent(attemptId)}/confirm`, "POST", {}));
}
