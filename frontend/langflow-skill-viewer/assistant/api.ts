import useAuthStore from "@/stores/authStore";

export class AssistantFailure extends Error {
  constructor(public code: string) {
    super(code);
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

export async function assistantRequest<T>(
  path: string,
  body?: unknown,
  signal?: AbortSignal,
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  const token = useAuthStore.getState().accessToken;
  if (token) headers.Authorization = `Bearer ${token}`;
  const controller = new AbortController();
  const abort = () => controller.abort();
  signal?.addEventListener("abort", abort, { once: true });
  if (signal?.aborted) controller.abort();
  const timer = window.setTimeout(abort, 20000);
  let response: Response;
  try {
    response = await fetch(`/api/v1/laomedo/assistant${path}`, {
      method: body === undefined ? "GET" : "POST",
      credentials: "same-origin",
      cache: "no-store",
      headers,
      signal: controller.signal,
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
  } catch (error) {
    if (signal?.aborted) throw error;
    throw new AssistantFailure(
      body === undefined
        ? "assistant_connection_unavailable"
        : "assistant_dispatch_unknown",
    );
  } finally {
    window.clearTimeout(timer);
    signal?.removeEventListener("abort", abort);
  }
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    if ([401, 403].includes(response.status))
      throw new AssistantFailure("assistant_session_locked");
    const code = payload?.detail?.code ?? payload?.code;
    throw new AssistantFailure(
      typeof code === "string" && /^[a-z][a-z0-9_]{0,100}$/.test(code)
        ? code
        : "assistant_connection_unavailable",
    );
  }
  if (!payload) throw new AssistantFailure("assistant_connection_unavailable");
  return payload as T;
}

export async function lockAssistant(): Promise<void> {
  // Sign-out must not skip chat revocation in upstream auto-login mode.
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), 3000);
  try {
    const status = await assistantRequest<{ available: boolean }>(
      "/status",
      undefined,
      controller.signal,
    );
    if (status.available)
      await assistantRequest("/lock", {}, controller.signal);
  } catch {
    // Native sign-out must continue even if chat is unavailable. The backend
    // logout path independently fences chat authority.
  } finally {
    window.clearTimeout(timer);
  }
}
