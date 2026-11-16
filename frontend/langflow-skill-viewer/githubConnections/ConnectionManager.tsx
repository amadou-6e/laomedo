import ConnectionNavigation from "./ConnectionNavigation";
import { ChevronDown, ChevronRight, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import useProfileSessionActions from "@/components/laomedoProfiles/useProfileSessionActions";
import ConnectionAccounts from "./ConnectionAccounts";
import ConnectionForms from "./ConnectionForms";
import ConnectionInventory from "./ConnectionInventory";
import ConnectionRegistration from "./ConnectionRegistration";
import {
  authorizationUrl,
  installationUrl,
  navigateToAuthorization,
  connectionCapability,
  connectionRequest,
  ConnectionFailure,
} from "./api";
import type { ConnectionAction, ConnectionIndex } from "./types";
import "./connections.css";
import catalogue from "@/components/laomedoErrors/node-error-catalog.json";

const channelName = "laomedo-private-connections";

export default function ConnectionManager() {
  return <ConnectionWorkspace />;
}

function ConnectionWorkspace() {
  const [enabled, setEnabled] = useState<boolean>();
  const [index, setIndex] = useState<ConnectionIndex>();
  const [view, setView] = useState<
    "list" | "detail" | "waiting" | "token" | "register" | "cleanup"
  >(() =>
    new URLSearchParams(window.location.search).get("registration") ===
    "unconfirmed"
      ? "register"
      : "list",
  );
  const [target, setTarget] = useState<string>();
  const [requestId, setRequestId] = useState<string | undefined>(() => {
    const query = new URLSearchParams(window.location.search);
    return (
      query.get("request") ??
      (query.has("setup_action")
        ? (query.get("state") ?? undefined)
        : undefined)
    );
  });
  const [busy, setBusy] = useState(false);
  const [showProgress, setShowProgress] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [tokenOpen, setTokenOpen] = useState(false);
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
      setShowProgress(!quiet);
      setError("");
      if (!quiet) {
        setNotice("");
        setIndex(undefined);
      }
      if (action && !["cleanup", "inventory"].includes(action)) {
        const channel = new BroadcastChannel(channelName);
        channel.postMessage({ type: "invalidate", source });
        channel.close();
        window.dispatchEvent(new Event("laomedo-private-data-invalidated"));
      }
      try {
        const result = await connectionRequest(action, payload);
        if (epoch.current !== current) return;
        setIndex(result.index);
        if (action && ["begin", "token", "edit"].includes(action)) {
          const outcome = result.outcome;
          if (
            typeof outcome === "object" &&
            outcome !== null &&
            "request_id" in outcome &&
            typeof outcome.request_id === "string" &&
            result.index.pending.some(
              (item) => item.request_id === outcome.request_id,
            )
          )
            setRequestId(outcome.request_id);
        }
        if (action === "confirm" || action === "cancel")
          setRequestId(undefined);
        if (action && !["cleanup", "inventory"].includes(action)) {
          const channel = new BroadcastChannel(channelName);
          channel.postMessage({ type: "invalidate", source });
          channel.close();
          window.dispatchEvent(new Event("laomedo-private-data-invalidated"));
        }
        return result;
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
              "github_connection_attempt_expired",
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
          setShowProgress(false);
        }
      }
    },
    [source],
  );

  useEffect(() => {
    let active = true;
    const query = new URLSearchParams(window.location.search);
    const outcome = query.get("outcome");
    connectionCapability().then(async (value) => {
      if (active) {
        setEnabled(value);
        if (value) {
          const loaded = await run();
          const installationReturn = query.get("state");
          const registeredAttempt = loaded?.index.pending.find(
            (item) =>
              item.request_id === installationReturn &&
              item.onboarding &&
              item.phase === "authorize" &&
              item.mode === "browser",
          );
          if (
            active &&
            query.get("setup_action") === "install" &&
            registeredAttempt
          ) {
            navigateToAuthorization(registeredAttempt.authorization_url);
            return;
          }
          if (
            active &&
            ["install", "update"].includes(query.get("setup_action") ?? "") &&
            installationReturn &&
            loaded?.index.pending.some(
              (item) =>
                item.request_id === installationReturn &&
                item.mode === "browser" &&
                item.phase === "consent",
            )
          )
            await run("inventory", { request_id: installationReturn }, true);
          if (active && loaded?.index.credential_cleanup_pending)
            await run("cleanup", {}, true);
          if (active && outcome && outcome !== "consent")
            setError(
              outcome === "signin-expired"
                ? "github_connection_attempt_expired"
                : "github_authorization_unconfirmed",
            );
        }
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
      setRequestId(undefined);
      setView("list");
      setTokenOpen(false);
      setBusy(false);
      setShowProgress(false);
      setNotice(
        "A connection changed in another tab. Check current state before continuing.",
      );
      window.dispatchEvent(new Event("laomedo-private-data-invalidated"));
    };
    if (query.has("outcome") || query.has("setup_action")) {
      window.history.replaceState(null, "", window.location.pathname);
    }
    return () => {
      active = false;
      ++epoch.current;
      channel.close();
    };
  }, [run, source]);

  const attempt = requestId
    ? index?.pending.find((item) => item.request_id === requestId)
    : index?.pending[0];
  useEffect(() => {
    if (view === "waiting" && index && !attempt && !busy) {
      setRequestId(undefined);
      setView(target ? "detail" : "list");
      setNotice(
        "This sign-in attempt is no longer available. Start again to continue.",
      );
    }
  }, [view, index, attempt, busy, target]);
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

  const returnToConnection = () => {
    setTokenOpen(false);
    setView(target ? "detail" : "list");
  };
  const begin = async (id?: string) => {
    setTarget(id);
    const selected = index?.connections.find(
      (item) => item.connection.id === id,
    );
    if (selected?.connection.mode === "token") {
      setView("token");
      return;
    }
    if (!id) {
      setTokenOpen(false);
      setView("register");
      return;
    }
    setView("waiting");
    await run("begin", id ? { connection_id: id } : {});
  };

  const entries =
    index?.connections.filter((item) => item.connection.state !== "revoked") ??
    [];
  const cleanupPending = target
    ? (index?.connections.find((item) => item.connection.id === target)
        ?.credential_cleanup_pending ?? index?.credential_cleanup_pending)
    : index?.credential_cleanup_pending;
  const waiting = attempt?.phase === "authorize";
  const focus =
    error ||
    view === "token" ||
    view === "register" ||
    view === "cleanup" ||
    attempt;
  return (
    <main
      className={`github-connections ${focus ? "gc-centered" : ""} ${view === "register" ? "gc-registration-page" : ""}`}
    >
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
              <Button
                ignoreTitleCase
                disabled={busy || !index}
                onClick={() => void begin()}
              >
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
            <div className="gc-screen">
              <section className="gc-panel gc-focus" role="alert">
                <h2>
                  {error === "github_connection_attempt_expired"
                    ? catalogue.github_connection_attempt_expired.title
                    : error === "private_session_required"
                      ? "Login required"
                      : "We couldn’t complete that"}
                </h2>
                <p className="gc-muted">
                  {error === "github_connection_attempt_expired"
                    ? catalogue.github_connection_attempt_expired.description
                    : error === "github_token_unsupported"
                      ? "Check your fine-grained personal access token and try again."
                      : error === "private_session_required"
                        ? "Log in to your local profile to continue."
                        : "We could not finish this request. Check current state to continue."}
                </p>
                {error === "private_session_required" && (
                  <Button
                    ignoreTitleCase
                    disabled={busy}
                    onClick={() => profile.signOut("logout")}
                  >
                    Log in
                  </Button>
                )}
              </section>
              {error !== "private_session_required" && (
                <ConnectionNavigation busy={busy} back={() => void run()} />
              )}
            </div>
          ) : attempt?.phase === "consent" ? (
            <ConnectionInventory
              key={attempt.request_id}
              attempt={attempt}
              manageAccess={
                attempt.mode === "browser"
                  ? installationUrl(
                      attempt.app_slug ?? undefined,
                      attempt.request_id,
                    )
                  : undefined
              }
              refresh={
                attempt.mode === "browser"
                  ? () =>
                      void run("inventory", { request_id: attempt.request_id })
                  : undefined
              }
              initialRepositoryIds={index?.connections
                .find((item) => item.connection.id === attempt.connection_id)
                ?.connection.repositories.map((repo) => repo.id)}
              busy={busy}
              confirm={async (ids) => {
                const result = await run("confirm", {
                  request_id: attempt.request_id,
                  repository_ids: ids,
                });
                if (result) {
                  setView(target ? "detail" : "list");
                  setNotice("");
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
                if (result) {
                  setTokenOpen(false);
                  setView("waiting");
                }
              }}
            />
          ) : view === "register" ? (
            <ConnectionRegistration
              busy={busy}
              close={returnToConnection}
              token={async (payload) => {
                const result = await run("token", payload);
                if (result) setView("waiting");
              }}
            />
          ) : view === "cleanup" ? (
            <div className="gc-screen">
              <section className="gc-panel gc-focus">
                <h2>
                  {target
                    ? cleanupPending
                      ? "Disconnected"
                      : "Connection removed"
                    : cleanupPending
                      ? "Credential cleanup"
                      : "Cleanup complete"}
                </h2>
                <p className="gc-muted">
                  {target
                    ? cleanupPending
                      ? "Laomedo has stopped using this account. Some saved credentials could not be removed."
                      : "Laomedo no longer uses this connection."
                    : cleanupPending
                      ? "Some credentials from earlier connections or sign-in attempts still need to be removed."
                      : "The saved credentials have been removed."}
                </p>
                {cleanupPending && (
                  <Button
                    ignoreTitleCase
                    disabled={busy}
                    onClick={() => void run("cleanup", {})}
                  >
                    Retry cleanup
                  </Button>
                )}
              </section>
              <ConnectionNavigation
                busy={busy}
                back={() => {
                  setTarget(undefined);
                  setView("list");
                }}
              />
            </div>
          ) : waiting ? (
            <div className="gc-screen">
              <section className="gc-panel gc-focus">
                <h2>Continue on GitHub</h2>
                <p className="gc-muted">
                  Continue to GitHub to authorize access. You’ll return here to
                  choose repositories.
                </p>
                <Button
                  ignoreTitleCase
                  disabled={
                    busy || !authorizationUrl(attempt.authorization_url)
                  }
                  onClick={() => {
                    navigateToAuthorization(attempt.authorization_url);
                  }}
                >
                  Continue to GitHub
                </Button>
                <div className="gc-advanced">
                  <button
                    type="button"
                    className="gc-link"
                    aria-expanded={tokenOpen}
                    aria-controls="gc-token-entry"
                    onClick={() => setTokenOpen(!tokenOpen)}
                  >
                    {tokenOpen ? (
                      <ChevronDown size={16} aria-hidden="true" />
                    ) : (
                      <ChevronRight size={16} aria-hidden="true" />
                    )}{" "}
                    Use a personal access token instead
                  </button>
                  {tokenOpen && (
                    <ConnectionForms
                      id="gc-token-entry"
                      inline
                      busy={busy}
                      close={() => setTokenOpen(false)}
                      submit={async (payload) => {
                        if (
                          !(await run("cancel", {
                            request_id: attempt.request_id,
                          }))
                        )
                          return;
                        const result = await run("token", {
                          ...payload,
                          ...(target ? { connection_id: target } : {}),
                        });
                        if (result) {
                          setTokenOpen(false);
                          setView("waiting");
                        }
                      }}
                    />
                  )}
                </div>
              </section>
              <ConnectionNavigation
                busy={busy}
                refresh={() => void run()}
                back={async () => {
                  if (await run("cancel", { request_id: attempt.request_id }))
                    returnToConnection();
                }}
              />
            </div>
          ) : index ? (
            <>
              <ConnectionAccounts
                refresh={() => void run()}
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
                  if (result) {
                    setTokenOpen(false);
                    setView("waiting");
                  }
                }}
                disconnect={async ({ connection }) => {
                  const result = await run("disconnect", {
                    connection_id: connection.id,
                    generation: connection.generation,
                  });
                  if (result) {
                    setTarget(connection.id);
                    setView("cleanup");
                  }
                }}
              />
              {index.credential_cleanup_pending && (
                <button
                  className="gc-link"
                  disabled={busy}
                  onClick={() => {
                    setTarget(undefined);
                    setView("cleanup");
                  }}
                >
                  Some saved sign-in details could not be removed. Retry cleanup
                </button>
              )}
            </>
          ) : (
            !busy && (
              <Button ignoreTitleCase onClick={() => void run()}>
                Check current state
              </Button>
            )
          )}
          {busy && showProgress && (
            <p role="status" className="gc-muted">
              Checking…
            </p>
          )}
          {!focus && view !== "detail" && (
            <button
              className="gc-link gc-refresh gc-icon"
              aria-label="Refresh"
              title="Refresh connections"
              disabled={busy}
              onClick={() => void run()}
            >
              <RefreshCw size={20} aria-hidden="true" />
            </button>
          )}
        </>
      )}
    </main>
  );
}
