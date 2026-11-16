/** Fixed destinations only; neither URL can carry credentials or a fragment. */
export function githubDestination(value, path, clientId) {
  const url = new URL(value);
  if (
    url.origin !== "https://github.com" ||
    url.pathname !== path ||
    url.username ||
    url.password ||
    url.hash ||
    (clientId && url.searchParams.get("client_id") !== clientId)
  ) {
    throw new Error("destination_refused");
  }
  return url.href;
}

/** Resolve only the exact request produced by this explicit sign-in operation. */
export function signInDestination(result, clientId) {
  const id = result?.outcome?.request_id;
  const attempt = result?.index?.pending?.find(
    (item) => item.request_id === id,
  );
  if (
    !id ||
    !attempt ||
    attempt.mode !== "browser" ||
    attempt.phase !== "authorize"
  ) {
    throw new Error("request_unconfirmed");
  }
  const url = githubDestination(
    attempt.authorization_url,
    "/login/oauth/authorize",
    clientId,
  );
  if (new URL(url).searchParams.get("prompt") !== "select_account") {
    throw new Error("picker_unconfirmed");
  }
  return url;
}

/** Use the current local-profile session; never import another credential. */
export async function request(action, payload, signal) {
  const allowed = new Set([undefined, "begin", "provision"]);
  if (!allowed.has(action)) throw new Error("action_refused");
  async function send(path, options = {}) {
    const response = await fetch(`/api/v1/laomedo/${path}`, {
      credentials: "same-origin",
      cache: "no-store",
      signal,
      ...options,
    });
    if (!response.ok)
      throw new Error(
        response.status === 401 || response.status === 403
          ? "login_required"
          : "request_failed",
      );
    return response.json();
  }
  if (!action) return send("github-connections");
  const session = await send("private-session");
  if (session.ready !== true || typeof session.csrf_token !== "string") {
    throw new Error("login_required");
  }
  return send(`github-connections/${action}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Laomedo-CSRF": session.csrf_token,
    },
    body: JSON.stringify(payload ?? {}),
  });
}
