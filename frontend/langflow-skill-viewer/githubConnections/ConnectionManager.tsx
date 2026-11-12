import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import ErrorExplanation from "@/components/laomedoErrors/ErrorExplanation";
import { describeNodeFailure } from "@/components/laomedoErrors/nodeErrors";
import useProfileSessionActions from "@/components/laomedoProfiles/useProfileSessionActions";
import ConnectionForms from "./ConnectionForms";
import ConnectionInventory from "./ConnectionInventory";
import {
  connectionCapability,
  connectionRequest,
  ConnectionFailure,
} from "./api";
import type { ConnectionAction, ConnectionIndex } from "./types";

const channelName = "laomedo-private-connections";

export default function ConnectionManager() {
  const [enabled, setEnabled] = useState<boolean>();
  const [index, setIndex] = useState<ConnectionIndex>();
  const [form, setForm] = useState<"setup" | "token">();
  const [advanced, setAdvanced] = useState(false);
  const [target, setTarget] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const epoch = useRef(0);
  const [source] = useState(() => crypto.randomUUID());
  const profile = useProfileSessionActions();
  const run = useCallback(
    async (action?: ConnectionAction, payload?: Record<string, unknown>) => {
      const current = ++epoch.current;
      setBusy(true);
      setError("");
      setNotice("");
      setIndex(undefined);
      if (action) {
        // Invalidate before sending: an unknown response can still have committed.
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
          setNotice(
            action === "disconnect"
              ? "Local disconnect checked. This does not revoke consent on GitHub."
              : "Current connection state checked.",
          );
        }
      } catch (failure) {
        if (epoch.current === current) {
          const definiteRefusal =
            failure instanceof ConnectionFailure &&
            [
              "github_connection_input_invalid",
              "github_token_unsupported",
              "private_request_refused",
            ].includes(failure.code);
          if (action && !definiteRefusal)
            setNotice(
              "The request may still be completing. Check current state before starting another action.",
            );
          setError(
            failure instanceof ConnectionFailure
              ? failure.code
              : "github_connection_unavailable",
          );
        }
      } finally {
        if (epoch.current === current) setBusy(false);
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
      setIndex(undefined);
      setForm(undefined);
      setBusy(false);
      setNotice(
        "A connection changed in another tab. Check current state before continuing.",
      );
      window.dispatchEvent(new Event("laomedo-private-data-invalidated"));
    };
    const query = new URLSearchParams(window.location.search);
    if (query.has("outcome")) {
      setNotice(
        query.get("outcome") === "consent"
          ? "GitHub returned. Check the verified account and select repository reads."
          : "Authorization was not confirmed. Check current state before starting a new sign-in.",
      );
      window.history.replaceState(null, "", window.location.pathname);
    }
    return () => {
      active = false;
      ++epoch.current;
      channel.close();
    };
  }, [run, source]);
  if (enabled === undefined) return <p>Checking connection availability…</p>;
  if (!enabled)
    return (
      <p>Private GitHub connections are not enabled in this deployment.</p>
    );
  const install =
    index?.app && /^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(index.app.slug)
      ? `https://github.com/apps/${index.app.slug}/installations/new`
      : undefined;
  return (
    <main className="grid w-full max-w-3xl gap-5 p-4">
      <div className="flex items-center justify-between gap-4">
        <h1 className="text-xl font-semibold">GitHub connections</h1>
        <Button variant="outline" disabled={busy} onClick={() => void run()}>
          Refresh
        </Button>
      </div>
      <p className="text-muted-foreground">
        Connect your GitHub account, then choose repositories to browse private skills.
      </p>
      {error && (
        <ErrorExplanation
          failure={describeNodeFailure(error, undefined, {
            operation: "GitHub connection",
          })}
        />
      )}
      {error === "private_session_required" && (
        <Button
          disabled={profile.busy}
          onClick={() => profile.signOut("logout")}
        >
          Sign in again
        </Button>
      )}
      {profile.notice}
      {notice && <p role="status">{notice}</p>}
      {busy && <p role="status">Checking…</p>}
      {index && (
        <>
          {(
            <section className="grid gap-3 rounded-lg border p-5">
              <h2 className="font-semibold">Connect your account</h2>
              <p className="text-sm text-muted-foreground">
                You choose which repositories Laomedo can read. This does not grant write access.
              </p>
              <div>
                <Button disabled={busy} onClick={() => {
                  if (index.app) void run("begin", {});
                  else { setForm("setup"); }
                }}>Connect GitHub</Button>
              </div>
              {!index.app && <p className="text-sm text-muted-foreground">
                GitHub sign-in needs a one-time setup on this local installation.
              </p>}
            </section>
          )}
          {form && (
            <section className="grid gap-4 rounded-lg border p-5">
            <ConnectionForms
              key={form + (target ?? "")}
              mode={form}
              busy={busy}
              close={() => {
                setForm(undefined);
                setTarget(undefined);
              }}
              submit={(payload) => {
                const action = form;
                setForm(undefined);
                void run(action === "setup" ? "setup" : "token", {
                  ...payload,
                  ...(target ? { connection_id: target } : {}),
                });
                setTarget(undefined);
              }}
            />

              {form === "setup" && (
                <div className="grid gap-1 text-sm text-muted-foreground">
                  <span>Callback URL ? copy this into your GitHub App</span>
                  <code className="break-all select-all">{index.callback_uri}</code>
                </div>
              )}
            </section>
          )}
          <details open={advanced} onToggle={(event) => setAdvanced(event.currentTarget.open)}
            className="rounded-lg border p-4">
            <summary className="cursor-pointer font-medium">Advanced</summary>
            <div className="mt-4 grid gap-4">
              <div className="flex flex-wrap gap-2">
                <Button variant="outline" disabled={busy} onClick={() => setForm("setup")}>
                  GitHub App setup
                </Button>
                <Button variant="outline" disabled={busy} onClick={() => {
                  setTarget(undefined); setForm("token");
                }}>Use a token instead</Button>
              </div>
              {install && <a className="text-sm underline" href={install} target="_blank" rel="noreferrer">
                Manage GitHub App installation
              </a>}
            </div>
          </details>
          {index.pending.map((attempt) =>
            attempt.phase === "consent" ? (
              <ConnectionInventory
                key={attempt.request_id}
                attempt={attempt}
                busy={busy}
                confirm={(ids) =>
                  void run("confirm", {
                    request_id: attempt.request_id,
                    repository_ids: ids,
                  })
                }
                cancel={() =>
                  void run("cancel", { request_id: attempt.request_id })
                }
              />
            ) : (
              <section
                key={attempt.request_id}
                className="grid gap-3 rounded border p-4"
              >
                <h2>Waiting for GitHub</h2>
                <p>
                  Return here after authorizing. Receiving a callback alone does
                  not grant repository reads.
                </p>
                {attempt.authorization_url && (
                  <Button
                    disabled={busy}
                    onClick={() => {
                      const url = new URL(attempt.authorization_url!);
                      if (
                        url.origin === "https://github.com" &&
                        url.pathname === "/login/oauth/authorize"
                      )
                        window.location.assign(url.href);
                    }}
                  >
                    Continue to GitHub
                  </Button>
                )}
                <Button
                  variant="outline"
                  disabled={busy}
                  onClick={() =>
                    void run("cancel", { request_id: attempt.request_id })
                  }
                >
                  Cancel sign-in
                </Button>
              </section>
            ),
          )}
          {index.connections.map(
            ({ connection, availability, credential_cleanup_pending }) => (
              <section
                key={connection.id}
                className="grid gap-2 rounded border p-4"
              >
                <h2 className="font-semibold">{connection.principal.login}</h2>
                <p>
                  {availability} · {connection.mode}
                </p>
                <ul>
                  {connection.repositories.map((repository) => (
                    <li key={repository.id}>{repository.full_name}</li>
                  ))}
                </ul>
                <div className="flex flex-wrap gap-2">
                  {connection.state !== "revoked" && (
                    <>
                      <Button
                        variant="outline"
                        disabled={busy}
                        onClick={() => {
                          if (connection.mode === "browser")
                            void run("begin", { connection_id: connection.id });
                          else {
                            setTarget(connection.id);
                            setAdvanced(true);
                            setForm("token");
                          }
                        }}
                      >
                        Reconnect / edit read access
                      </Button>
                      <Button
                        variant="outline"
                        disabled={busy}
                        onClick={() =>
                          void run("disconnect", {
                            connection_id: connection.id,
                            generation: connection.generation,
                          })
                        }
                      >
                        Disconnect locally
                      </Button>
                    </>
                  )}
                  {credential_cleanup_pending && (
                    <p>Local credential removal is incomplete.</p>
                  )}
                </div>
              </section>
            ),
          )}
          {index.credential_cleanup_pending && (
            <Button
              variant="outline"
              disabled={busy}
              onClick={() => void run("cleanup", {})}
            >
              Retry local credential cleanup
            </Button>
          )}
        </>
      )}
    </main>
  );
}
