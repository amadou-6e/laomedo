import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { createRequire } from "node:module";

const require = createRequire(
  process.env.PILOT_FRONTEND_PACKAGE ?? import.meta.url,
);
const { JSDOM } = require("jsdom");
const settle = () => new Promise((resolve) => setImmediate(resolve));

test("profile change clears private labels and fences a late sign-in response", async () => {
  const dom = new JSDOM(
    await readFile(new URL("./index.html", import.meta.url), "utf8"),
  );
  const previous = {
    window: globalThis.window,
    document: globalThis.document,
    fetch: globalThis.fetch,
    BroadcastChannel: globalThis.BroadcastChannel,
  };
  const windows = new EventTarget();
  const navigations = [];
  windows.location = {
    assign: (url) => navigations.push(url),
    replace: (url) => navigations.push(url),
  };
  const channels = new Map();
  class Channel {
    postMessage() {}
    constructor(name) {
      channels.set(name, this);
    }
  }
  const calls = [];
  let finishBegin;
  const label = "<img src=x onerror=alert(1)>";
  globalThis.window = windows;
  globalThis.document = dom.window.document;
  globalThis.BroadcastChannel = Channel;
  globalThis.fetch = async (path, options) => {
    calls.push({ path, options });
    if (path.endsWith("/begin"))
      return new Promise((resolve) => {
        finishBegin = resolve;
      });
    return {
      ok: true,
      json: async () =>
        path.endsWith("private-session")
          ? { ready: true, csrf_token: "synthetic" }
          : {
              index: {
                apps: [
                  { id: "app-one", slug: "app-one", client_id: "client-one", principal: {id: 11, login: label} },
                  { id: "unknown", slug: "unknown", client_id: "unknown" },
                ],
                connections: [
                  {
                    availability: "ready",
                    connection: {
                      id: "connection-one",
                      app_id: "app-one",
                      mode: "browser",
                      state: "ready",
                      principal: { id: 11, login: label },
                    },
                  },
                ],
              },
            },
    };
  };
  try {
    await import("./pilot.js");
    await settle();
    assert.equal(
      calls.length,
      1,
      "render must not start a sign-in or provisioning mutation",
    );
    assert.equal(document.querySelectorAll("#accounts img").length, 0);
    assert.ok(document.querySelector("#accounts").textContent.includes(label));
    assert.equal(document.querySelectorAll("#accounts button").length, 1);
    assert.equal(document.querySelector("#accounts a").getAttribute("href"), "/settings/github");
    document.getElementById("add").click();
    assert.equal(document.getElementById("setup").hidden, false);
    assert.equal(calls.length, 1, "opening setup must still wait for Continue");
    document.getElementById("back").click();
    document.querySelector("#accounts button").click();
    await settle();
    assert.equal(
      JSON.parse(calls.at(-1).options.body).connection_id,
      "connection-one",
    );
    channels
      .get("laomedo-local-profile-context")
      .onmessage({ data: { type: "profile-context-changed" } });
    assert.equal(document.getElementById("accounts").children.length, 0);
    finishBegin({
      ok: true,
      json: async () => ({
        outcome: { request_id: "ours" },
        index: {
          pending: [
            {
              request_id: "ours",
              mode: "browser",
              phase: "authorize",
              authorization_url:
                "https://github.com/login/oauth/authorize?client_id=client-one&prompt=select_account",
            },
          ],
        },
      }),
    });
    await settle();
    assert.deepEqual(
      navigations,
      ["/login"],
      "old profile's response must not navigate to GitHub",
    );
    assert.equal(document.getElementById("accounts").children.length, 0);
  } finally {
    Object.assign(globalThis, previous);
    dom.window.close();
  }
});
