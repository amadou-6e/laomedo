import catalogue from "@/components/laomedoErrors/node-error-catalog.json";
import { ConnectionFailure } from "@/components/laomedoGitHubConnections/api";
import type { PrivateSelection } from "./models";

async function read(path: string, options: RequestInit, signal?: AbortSignal) {
  let response: Response;
  try {
    response = await fetch(`/api/v1/laomedo/${path}`, { ...options, credentials: "same-origin", cache: "no-store",
      signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(120000)]) : AbortSignal.timeout(120000) });
  } catch { throw new ConnectionFailure("github_connection_unavailable"); }
  let body: any;
  try { body = await response.json(); } catch { throw new ConnectionFailure("github_connection_unavailable"); }
  if (!response.ok) throw new ConnectionFailure(typeof body?.code === "string" && Object.hasOwn(catalogue, body.code)
    ? body.code : "github_connection_unavailable");
  return body;
}

export async function privateSkillRequest<T>(action: "discover" | "revisions" | "inspect" | "history" | "compare",
  selection: PrivateSelection, fields: Record<string, unknown> = {}, signal?: AbortSignal): Promise<T> {
  const session = await read("private-session", { headers: {} }, signal);
  if (session?.ready !== true || typeof session.csrf_token !== "string") throw new ConnectionFailure("private_session_required");
  return read(`private-skills/${action}`, { method: "POST", headers: { "Content-Type": "application/json", "X-Laomedo-CSRF": session.csrf_token },
    body: JSON.stringify({ ...fields, connection_id: selection.connectionId, repository_id: selection.repositoryId }) }, signal);
}

/** Clear local private bytes before any obsolete async result can be used. */
export function subscribePrivateInvalidation(clear: () => void) {
  const connections = typeof BroadcastChannel === "function" ? new BroadcastChannel("laomedo-private-connections") : undefined;
  const profiles = typeof BroadcastChannel === "function" ? new BroadcastChannel("laomedo-local-profile-context") : undefined;
  if (connections) connections.onmessage = (event) => { if (event.data?.type === "invalidate") clear(); };
  if (profiles) profiles.onmessage = (event) => { if (event.data?.type === "profile-context-changed") clear(); };
  window.addEventListener("laomedo-private-data-invalidated", clear);
  const restore = (event: PageTransitionEvent) => { if (event.persisted) clear(); };
  window.addEventListener("pageshow", restore);
  return () => { connections?.close(); profiles?.close(); window.removeEventListener("laomedo-private-data-invalidated", clear); window.removeEventListener("pageshow", restore); };
}
