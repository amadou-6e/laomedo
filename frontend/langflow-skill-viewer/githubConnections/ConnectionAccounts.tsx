import { Button } from "@/components/ui/button";
import type { ConnectionIndex } from "./types";

type Entry = ConnectionIndex["connections"][number];

export default function ConnectionAccounts({
  entries,
  selected,
  busy,
  select,
  back,
  edit,
  reconnect,
  disconnect,
  token,
}: {
  entries: Entry[];
  selected?: string;
  busy: boolean;
  select: (id: string) => void;
  back: () => void;
  edit: (id: string) => void;
  reconnect: (id: string) => void;
  disconnect: (entry: Entry) => void;
  token: (id: string) => void;
}) {
  const entry = entries.find(({ connection }) => connection.id === selected);
  if (entry) {
    const { connection, availability } = entry;
    const ready = availability === "ready";
    return (
      <section className="gc-panel gc-detail">
        <button className="gc-link gc-back" disabled={busy} onClick={back}>
          ← GitHub connections
        </button>
        <div className="gc-identity">
          <span className="gc-avatar" aria-hidden="true">
            {connection.principal.login[0]?.toUpperCase()}
          </span>
          <h2>@{connection.principal.login}</h2>
          <span className={`gc-status ${ready ? "gc-ready" : "gc-attention"}`}>
            {ready ? "Connected" : "Sign-in required"}
          </span>
        </div>
        <p className="gc-muted">
          {ready
            ? "Access is maintained automatically when supported."
            : "Sign in again to restore access for this account."}
        </p>
        {!ready && (
          <Button disabled={busy} onClick={() => reconnect(connection.id)}>
            Sign in again
          </Button>
        )}
        <div className="gc-section">
          <h3>Repository access</h3>
          <ul className="gc-repositories">
            {connection.repositories.map((repo) => (
              <li key={repo.id}>{repo.full_name}</li>
            ))}
          </ul>
          {ready && (
            <Button
              variant="outline"
              disabled={busy}
              onClick={() => edit(connection.id)}
            >
              Change repositories
            </Button>
          )}
        </div>
        {connection.mode === "token" && (
          <details className="gc-advanced">
            <summary>Advanced</summary>
            <button
              className="gc-link"
              disabled={busy}
              onClick={() => token(connection.id)}
            >
              Replace token
            </button>
          </details>
        )}
        <div className="gc-footer">
          <p className="gc-muted">
            Removing this connection stops Laomedo access.
          </p>
          <Button
            variant="outline"
            disabled={busy}
            onClick={() => disconnect(entry)}
          >
            Disconnect
          </Button>
        </div>
      </section>
    );
  }
  return (
    <section
      className="gc-panel gc-accounts"
      aria-label="Saved GitHub connections"
    >
      {!entries.length ? (
        <div className="gc-empty">
          <h2>No connections yet</h2>
          <p className="gc-muted">
            Add your GitHub account to choose the repositories Laomedo can read.
          </p>
        </div>
      ) : (
        <>
          <h2 className="gc-eyebrow">Connected accounts</h2>
          {entries.map((item) => {
            const { connection, availability } = item;
            const ready = availability === "ready";
            return (
              <div className="gc-account-row" key={connection.id}>
                <span className="gc-avatar" aria-hidden="true">
                  {connection.principal.login[0]?.toUpperCase()}
                </span>
                <div className="gc-account-copy">
                  <h3>@{connection.principal.login}</h3>
                  <p className="gc-muted">
                    {connection.repositories.length}{" "}
                    {connection.repositories.length === 1
                      ? "repository"
                      : "repositories"}{" "}
                    ·{" "}
                    {connection.repositories
                      .map((repo) => repo.full_name)
                      .join(", ")}
                  </p>
                </div>
                <span
                  className={`gc-status ${ready ? "gc-ready" : "gc-attention"}`}
                >
                  {ready ? "Connected" : "Sign-in required"}
                </span>
                <Button
                  variant="outline"
                  disabled={busy}
                  onClick={() => select(connection.id)}
                >
                  View connection
                </Button>
              </div>
            );
          })}
        </>
      )}
    </section>
  );
}
