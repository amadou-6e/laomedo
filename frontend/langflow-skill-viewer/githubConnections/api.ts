import catalogue from "@/components/laomedoErrors/node-error-catalog.json";
import type { ConnectionAction, ConnectionResult } from "./types";

export class ConnectionFailure extends Error {
  constructor(public code: string) {
    super(code);
  }
}

async function request(path: string, options: RequestInit = {}) {
  // The pinned native interceptor writes locale headers in place, including GET.
  const headers = Object.fromEntries(new Headers(options.headers).entries());
  let response: Response;
  try {
    response = await fetch(`/api/v1/laomedo/${path}`, {
      ...options,
      headers,
      credentials: "same-origin",
      cache: "no-store",
      signal: AbortSignal.timeout(120000),
    });
  } catch {
    throw new ConnectionFailure("github_connection_unavailable");
  }
  let body: any;
  try {
    body = await response.json();
  } catch {
    throw new ConnectionFailure("github_connection_unavailable");
  }
  if (!response.ok) {
    const code =
      typeof body?.code === "string" && Object.hasOwn(catalogue, body.code)
        ? body.code
        : "github_connection_unavailable";
    throw new ConnectionFailure(code);
  }
  return body;
}

export async function connectionCapability(): Promise<boolean> {
  try {
    const value = await request("github-connections-capability");
    return value?.enabled === true;
  } catch {
    return false;
  }
}

export async function connectionRequest(
  action?: ConnectionAction,
  payload?: Record<string, unknown>,
): Promise<ConnectionResult> {
  let value: any;
  if (action) {
    const session = await request("private-session");
    if (session?.ready !== true || typeof session.csrf_token !== "string")
      throw new ConnectionFailure("private_session_required");
    value = await request(`github-connections/${action}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Laomedo-CSRF": session.csrf_token,
      },
      body: JSON.stringify(payload ?? {}),
    });
  } else value = await request("github-connections");
  if (
    !Number.isSafeInteger(value?.index?.revision) ||
    !Array.isArray(value.index.connections) ||
    !Array.isArray(value.index.pending)
  )
    throw new ConnectionFailure("github_connection_unavailable");
  return value;
}
