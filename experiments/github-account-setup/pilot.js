import { githubDestination, request, signInDestination } from "./api.js";

const byId = (id) => document.getElementById(id);
let busy = false;
let epoch = 0;
let controller;

function clearPrivateView() {
  byId("accounts").replaceChildren();
  byId("accounts").hidden = false;
  byId("actions").hidden = false;
  byId("setup").hidden = true;
  byId("error").hidden = true;
  byId("login").hidden = true;
}

function invalidate() {
  ++epoch;
  controller?.abort();
  clearPrivateView();
  busy = false;
  document.querySelectorAll("button").forEach((button) => {
    button.disabled = false;
  });
  byId("status").textContent =
    "Your session or connections changed. Refresh to continue.";
}

async function run(operation) {
  if (busy) return;
  busy = true;
  const current = ++epoch;
  controller = new AbortController();
  byId("error").hidden = true;
  byId("login").hidden = true;
  document.querySelectorAll("button").forEach((button) => {
    button.disabled = true;
  });
  try {
    await operation(controller.signal, () => current === epoch);
  } catch (error) {
    if (current !== epoch) return;
    clearPrivateView();
    byId("status").textContent = "";
    byId("error").hidden = false;
    const login = error.message === "login_required";
    byId("error").textContent = login
      ? "Log in to your local Laomedo profile, then return here and Refresh."
      : "This step could not be confirmed. Refresh before trying again. If you approved App creation on GitHub, check your GitHub Apps before starting another setup.";
    byId("login").hidden = !login;
  } finally {
    if (current === epoch) {
      busy = false;
      document.querySelectorAll("button").forEach((button) => {
        button.disabled = false;
      });
    }
  }
}

function signIn(app, connectionId) {
  void run(async (signal, valid) => {
    byId("status").textContent = "Opening GitHub’s account picker…";
    const result = await request(
      "begin",
      connectionId ? { connection_id: connectionId } : { app_id: app.id },
      signal,
    );
    if (!valid()) return;
    window.location.assign(signInDestination(result, app.client_id));
  });
}

function accountRow(principal, subtitle, app, connectionId) {
  const row = document.createElement("article");
  row.className = "account";
  const icon = document.createElement("span");
  icon.className = "avatar";
  icon.setAttribute("aria-hidden", "true");
  icon.textContent = (principal?.login ?? app.slug).slice(0, 1).toUpperCase();
  const details = document.createElement("div");
  const name = document.createElement("h2");
  name.textContent = principal ? `@${principal.login}` : app.slug;
  const note = document.createElement("p");
  note.className = "muted";
  note.textContent = subtitle;
  details.append(name, note);
  const button = document.createElement("button");
  button.type = "button";
  button.className = "secondary";
  button.textContent = "Sign in";
  button.setAttribute(
    "aria-label",
    `Sign in to ${principal?.login ?? app.slug}`,
  );
  button.onclick = () => signIn(app, connectionId);
  row.append(icon, details, button);
  byId("accounts").append(row);
}

function load() {
  void run(async (signal, valid) => {
    clearPrivateView();
    byId("status").textContent = "Loading your connections…";
    const result = await request(undefined, undefined, signal);
    if (!valid()) return;
    const index = result.index;
    if (!Array.isArray(index?.connections) || !Array.isArray(index?.apps))
      throw new Error("inventory_unconfirmed");
    const used = new Set();
    for (const { connection, availability } of index.connections) {
      if (connection.mode !== "browser" || connection.state === "revoked")
        continue;
      const app = index.apps.find((item) => item.id === connection.app_id);
      if (!app) continue;
      used.add(app.id);
      accountRow(
        connection.principal,
        availability === "ready"
          ? "Connected · private App already set up"
          : "Private App already set up · sign in again",
        app,
        connection.id,
      );
    }
    for (const app of index.apps) {
      if (!used.has(app.id))
        accountRow(
          app.principal,
          app.principal
            ? "Private App registered · finish connecting"
            : "Existing App · verify the owner on GitHub",
          app,
        );
    }
    byId("status").textContent = byId("accounts").children.length
      ? "Sign in with an existing private App, or set up another account."
      : "Set up your first private GitHub connection.";
  });
}

byId("add").onclick = () => {
  byId("accounts").hidden = true;
  byId("actions").hidden = true;
  byId("setup").hidden = false;
  byId("status").textContent = "";
  byId("setup-title").tabIndex = -1;
  byId("setup-title").focus();
};
byId("back").onclick = () => {
  byId("accounts").hidden = false;
  byId("actions").hidden = false;
  byId("setup").hidden = true;
  byId("add").focus();
};
byId("refresh").onclick = load;
byId("register").onclick = () => {
  void run(async (signal, valid) => {
    byId("status").textContent = "Preparing your private App…";
    const result = await request("provision", {}, signal);
    if (!valid()) return;
    const { action, manifest } = result.outcome ?? {};
    if (!manifest || manifest.public !== false)
      throw new Error("manifest_unconfirmed");
    const form = document.createElement("form");
    form.method = "post";
    form.action = githubDestination(action, "/settings/apps/new");
    const input = document.createElement("input");
    input.type = "hidden";
    input.name = "manifest";
    input.value = JSON.stringify(manifest);
    form.append(input);
    document.body.append(form);
    form.submit();
    form.remove();
  });
};
window.addEventListener("pagehide", invalidate);
window.addEventListener("pageshow", (event) => {
  if (event.persisted) load();
});
const channel = new BroadcastChannel("laomedo-private-connections");
channel.onmessage = (event) => {
  if (event.data?.type === "invalidate") invalidate();
};
window.addEventListener("laomedo-private-data-invalidated", invalidate);
const profiles = new BroadcastChannel("laomedo-local-profile-context");
profiles.onmessage = (event) => {
  if (event.data?.type === "profile-context-changed") {
    invalidate();
    window.location.replace("/login");
  }
};
load();
