import test from "node:test";
import assert from "node:assert/strict";
import { githubDestination, signInDestination, request } from "./api.js";

test("registration cannot leave GitHub's exact registration endpoint", () => {
  for (const value of [
    "https://github.com.evil.test/settings/apps/new",
    "http://github.com/settings/apps/new",
    "https://user@github.com/settings/apps/new",
    "https://github.com/settings/apps/new#anything",
    "https://github.com/login",
  ]) {
    assert.throws(() => githubDestination(value, "/settings/apps/new"));
  }
  assert.equal(
    githubDestination(
      "https://github.com/settings/apps/new?state=bound",
      "/settings/apps/new",
    ),
    "https://github.com/settings/apps/new?state=bound",
  );
});

test("sign-in uses its own pending request, App and native picker", () => {
  const correct =
    "https://github.com/login/oauth/authorize?client_id=private-b&prompt=select_account";
  const result = {
    outcome: { request_id: "ours" },
    index: {
      pending: [
        {
          request_id: "other",
          mode: "browser",
          phase: "authorize",
          authorization_url: "https://evil.test",
        },
        {
          request_id: "ours",
          mode: "browser",
          phase: "authorize",
          authorization_url: correct,
        },
      ],
    },
  };
  assert.equal(signInDestination(result, "private-b"), correct);
  assert.throws(() => signInDestination(result, "private-a"));
  result.outcome.request_id = "missing";
  assert.throws(() => signInDestination(result, "private-b"));
  result.outcome.request_id = "ours";
  result.index.pending[1].authorization_url =
    "https://github.com/login/oauth/authorize?client_id=private-b";
  assert.throws(() => signInDestination(result, "private-b"));
});

test("writes require current CSRF admission and preserve exact explicit App binding", async () => {
  const previous = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (path, options) => {
    calls.push({ path, options });
    return {
      ok: true,
      json: async () =>
        path.endsWith("private-session")
          ? { ready: true, csrf_token: "synthetic-csrf" }
          : { outcome: {} },
    };
  };
  try {
    await request("begin", { app_id: "private-app-id" });
    assert.equal(calls[0].path, "/api/v1/laomedo/private-session");
    assert.equal(calls[1].options.headers["X-Laomedo-CSRF"], "synthetic-csrf");
    assert.equal(calls[1].options.body, '{"app_id":"private-app-id"}');
    assert.equal(calls[1].options.credentials, "same-origin");
    globalThis.fetch = async () => ({
      ok: true,
      json: async () => ({ ready: false }),
    });
    await assert.rejects(request("provision", {}), /login_required/);
    await assert.rejects(request("disconnect", {}), /action_refused/);
  } finally {
    globalThis.fetch = previous;
  }
});
