import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import useProfileSessionActions from "@/components/laomedoProfiles/useProfileSessionActions";
import ConnectionAccounts from "./ConnectionAccounts";
import ConnectionForms from "./ConnectionForms";
import ConnectionInventory from "./ConnectionInventory";
import {
  authorizationUrl,
  connectionCapability,
  connectionRequest,
  ConnectionFailure,
} from "./api";
import type { ConnectionAction, ConnectionIndex } from "./types";
import "./connections.css";

const channelName = "laomedo-private-connections";

export default function ConnectionManager() {
  const [enabled, setEnabled] = useState<boolean>();
  const [index, setIndex] = useState<ConnectionIndex>();
  const [view, setView] = useState<
    "list" | "detail" | "waiting" | "token" | "unavailable" | "cleanup"
  >("list");
  const [target, setTarget] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const epoch = useRef(0);
  const inFlight = useRef(false);
  const [source] = useState(() => crypto.randomUUID());
  const profile = useProfileSessionActions();
  const run = useCallback(
    async (
      action?: ConnectionAction,
      payload?: Record<string, unknown>,
      quiet = false,
    ) => {
      if (inFlight.current) return;
      const current = ++epoch.current;
      inFlight.current = true;
      setBusy(true);
      setError("");
      if (!quiet) {
        setNotice("");
        setIndex(undefined);
      }
      if (action) {
        const channel = new BroadcastChannel(channelName);
        channel.postMessage({ type: "invalidate", source });
        channel.close();
        window.dispatchEvent(new Event("laomedo-private-data-invalidated"));
      }
      try {
        const result = await connectionRequest(action, payload);
        if (epoch.current !== current) return;
        setIndex(result.index);
        if (action) {
          const channel = new BroadcastChannel(channelName);
          channel.postMessage({ type: "invalidate", source });
          channel.close();
          window.dispatchEvent(new Event("laomedo-private-data-invalidated"));
        }
        return result.index;
      } catch (failure) {
        if (epoch.current === current) {
          setIndex(undefined);
          const code =
            failure instanceof ConnectionFailure
              ? failure.code
              : "github_connection_unavailable";
          setError(code);
          if (
            action &&
            ![
              "github_connection_input_invalid",
              "github_token_unsupported",
              "private_request_refused",
            ].includes(code)
          )
            setNotice(
              "The request may still be completing. Check current state before trying again.",
            );
        }
      } finally {
        if (epoch.current === current) {
          inFlight.current = false;
          setBusy(false);
        }
      }
    },
    [source],
  );

  useEffect(() => {
    let active = true;
    connectionCapability().then((value) => {
      if (active) {
        setEnabled(value);
        if (value) void run();
      }
    });
    const channel = new BroadcastChannel(channelName);
    channel.onmessage = (event) => {
      if (event.data?.type !== "invalidate" || event.data?.source === source)
        return;
      ++epoch.current;
      inFlight.current = false;
      setIndex(undefined);
      setTarget(undefined);
      setView("list");
      setBusy(false);
      setNotice(
        "A connection changed in another tab. Check current state before continuing.",
      );
      window.dispatchEvent(new Event("laomedo-private-data-invalidated"));
    };
    const query = new URLSearchParams(window.location.search);
    if (query.has("outcome")) {
      if (query.get("outcome") !== "consent")
        setError("github_authorization_unconfirmed");
      window.history.replaceState(null, "", window.location.pathname);
    }
    return () => {
      active = false;
      ++epoch.current;
      channel.close();
    };
  }, [run, source]);

  const attempt = index?.pending[0];
  // Only read status while waiting. Never replay an exchange or mutation.
  useEffect(() => {
    if (attempt?.phase !== "authorize" || error) return;
    const check = () => {
      if (document.visibilityState === "visible")
        void run(undefined, undefined, true);
    };
    window.addEventListener("focus", check);
    const timer = window.setInterval(check, 3000);
    return () => {
      window.removeEventListener("focus", check);
      window.clearInterval(timer);
    };
  }, [attempt?.phase, error, run]);

  const returnToConnection = () => setView(target ? "detail" : "list");
  const begin = async (id?: string) => {
    setTarget(id);
    const selected = index?.connections.find(
      (item) => item.connection.id === id,
    );
    if (selected?.connection.mode === "token") {
      setView("token");
      return;
    }
    if (!index?.app) {
      setView("unavailable");
      return;
    }
    // Reserve a tab within the user gesture so async CSRF/network work does not block opening it.
    const popup = window.open("about:blank", "_blank");
    if (popup) popup.opener = null;
    setView("waiting");
    const result = await run("begin", id ? { connection_id: id } : {});
    const pending = result?.pending.find(
      (item) =>
        item.connection_id === id || (!id && item.phase === "authorize"),
    );
    const url = authorizationUrl(pending?.authorization_url);
    if (url && popup && !popup.closed) popup.location.replace(url);
    else if (popup && !popup.closed) popup.close();
  };

  const entries =
    index?.connections.filter((item) => item.connection.state !== "revoked") ??
    [];
  const waiting = attempt?.phase === "authorize";
  const focus =
    error ||
    view === "token" ||
    view === "unavailable" ||
    view === "cleanup" ||
    attempt;
  return (
    <main className={`github-connections ${focus ? "gc-centered" : ""}`}>
      {enabled === undefined && (
        <p role="status">Checking connection availability…</p>
      )}
      {enabled === false && (
        <section className="gc-panel gc-focus">
          <h2>GitHub connections unavailable</h2>
          <p className="gc-muted">
            Connections are not enabled in this installation.
          </p>
        </section>
      )}
      {enabled && (
        <>
          {!focus && (
            <header className="gc-heading">
              <div>
                <h1>GitHub connections</h1>
                <p className="gc-muted">
                  Manage the GitHub accounts Laomedo can use.
                </p>
              </div>
              <Button disabled={busy || !index} onClick={() => void begin()}>
                + Add connection
              </Button>
            </header>
          )}
          {notice && (
            <p role="status" className="gc-notice">
              {notice}
            </p>
          )}
          {profile.notice}
          {error ? (
            <section className="gc-panel gc-focus" role="alert">
              <h2>
                {error === "private_session_required"
                  ? "Login required"
                  : "We couldn’t complete that"}
              </h2>
              <p className="gc-muted">
                {error === "github_token_unsupported"
                  ? "Check your fine-grained personal access token and try again."
                  : error === "private_session_required"
                    ? "Log in to your local profile to continue."
                    : "We could not finish this request. Check current state to continue."}
              </p>
              <Button
                disabled={busy}
                onClick={() =>
                  error === "private_session_required"
                    ? profile.signOut("logout")
                    : void run()
                }
              >
                {error === "private_session_required"
                  ? "Log in"
                  : "Check current state"}
              </Button>
            </section>
          ) : attempt?.phase === "consent" ? (
            <ConnectionInventory
              key={attempt.request_id}
              attempt={attempt}
              busy={busy}
              confirm={async (ids) => {
                const result = await run("confirm", {
                  request_id: attempt.request_id,
                  repository_ids: ids,
                });
                if (result) {
                  setView(target ? "detail" : "list");
                  setNotice("Connection saved.");
                }
              }}
              cancel={async () => {
                if (await run("cancel", { request_id: attempt.request_id }))
                  returnToConnection();
              }}
            />
          ) : view === "token" ? (
            <ConnectionForms
              key={target ?? "new"}
              busy={busy}
              close={returnToConnection}
              submit={async (payload) => {
                const result = await run("token", {
                  ...payload,
                  ...(target ? { connection_id: target } : {}),
                });
                if (result) setView("waiting");
              }}
            />
          ) : view === "unavailable" ? (
            <section className="gc-panel gc-focus">
              <h2>GitHub is unavailable</h2>
              <p className="gc-muted">
                We could not connect to GitHub right now. Your saved connections
                have not changed.
              </p>
              <Button
                disabled={busy}
                onClick={async () => {
                  const result = await run();
                  if (result?.app) setView("list");
                }}
              >
                Try again
              </Button>
              <Button variant="ghost" onClick={returnToConnection}>
                Go back
              </Button>
              <button
                className="gc-link gc-muted"
                onClick={() => setView("token")}
              >
                Advanced: use a personal access token
              </button>
            </section>
          ) : view === "cleanup" ? (
            <section className="gc-panel gc-focus">
              <h2>
                {index?.credential_cleanup_pending
                  ? "Disconnected"
                  : "Connection removed"}
              </h2>
              <p className="gc-muted">
                {index?.credential_cleanup_pending
                  ? "Laomedo has stopped using this account. Some saved credentials could not be removed."
                  : "Laomedo no longer uses this connection."}
              </p>
              {index?.credential_cleanup_pending && (
                <Button disabled={busy} onClick={() => void run("cleanup", {})}>
                  Retry cleanup
                </Button>
              )}
              <Button
                variant="ghost"
                onClick={() => {
                  setTarget(undefined);
                  setView("list");
                }}
              >
                Close
              </Button>
            </section>
          ) : waiting ? (
            <section className="gc-panel gc-focus">
              <h2>Continue on GitHub</h2>
              <p className="gc-muted">
                We opened GitHub to finish connecting your account. Return here
                after you authorize access.
              </p>
              <Button
                disabled={busy || !authorizationUrl(attempt.authorization_url)}
                onClick={() => {
                  const url = authorizationUrl(attempt.authorization_url);
                  if (url) window.open(url, "_blank", "noopener,noreferrer");
                }}
              >
                Open GitHub again
              </Button>
              <p className="gc-muted gc-small">
                If GitHub did not open, use the button above.
              </p>
              <button
                className="gc-link"
                disabled={busy}
                onClick={async () => {
                  if (await run("cancel", { request_id: attempt.request_id }))
                    setView("token");
                }}
              >
                Advanced: use a personal access token
              </button>
              <Button
                variant="ghost"
                disabled={busy}
                onClick={async () => {
                  if (await run("cancel", { request_id: attempt.request_id }))
                    returnToConnection();
                }}
              >
                Cancel
              </Button>
            </section>
          ) : index ? (
            <>
              <ConnectionAccounts
                entries={entries}
                selected={view === "detail" ? target : undefined}
                busy={busy}
                select={(id) => {
                  setTarget(id);
                  setView("detail");
                }}
                back={() => {
                  setTarget(undefined);
                  setView("list");
                }}
                reconnect={(id) => void begin(id)}
                token={(id) => {
                  setTarget(id);
                  setView("token");
                }}
                edit={async (id) => {
                  setTarget(id);
                  const result = await run("edit", { connection_id: id });
                  if (result) setView("waiting");
                }}
                disconnect={async ({ connection }) => {
                  const result = await run("disconnect", {
                    connection_id: connection.id,
                    generation: connection.generation,
                  });
                  if (result) {
                    setTarget(undefined);
                    setView("cleanup");
                  }
                }}
              />
              {index.credential_cleanup_pending && (
                <button
                  className="gc-link"
                  disabled={busy}
                  onClick={() => setView("cleanup")}
                >
                  Review credential cleanup
                </button>
              )}
            </>
          ) : (
            !busy && (
              <Button onClick={() => void run()}>Check current state</Button>
            )
          )}
          {busy && (
            <p role="status" className="gc-muted">
              Checking…
            </p>
          )}
          {!focus && (
            <button
              className="gc-link gc-refresh"
              disabled={busy}
              onClick={() => void run()}
            >
              Refresh
            </button>
          )}
        </>
      )}
    </main>
  );
}
