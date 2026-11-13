import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { PendingConnection } from "./types";

export default function ConnectionInventory({
  attempt,
  busy,
  confirm,
  cancel,
}: {
  attempt: PendingConnection;
  busy: boolean;
  confirm: (ids: number[]) => void;
  cancel: () => void;
}) {
  const [selected, setSelected] = useState<number[]>([]);
  const [query, setQuery] = useState("");
  const inventory = attempt.inventory;
  if (!inventory) return null;
  return (
    <section className="gc-panel gc-consent">
      <h2>Choose repositories</h2>
      <p className="gc-muted">
        Choose what Laomedo may read. You can change this later.
      </p>
      <div className="gc-identity">
        <span className="gc-avatar" aria-hidden="true">
          {inventory.principal.login[0]?.toUpperCase()}
        </span>
        <strong>@{inventory.principal.login}</strong>
      </div>
      <Input
        aria-label="Search repositories"
        placeholder="Search repositories"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
      />
      <div className="gc-choices">
        {inventory.repositories
          .filter((repo) =>
            repo.full_name.toLowerCase().includes(query.toLowerCase()),
          )
          .map((repo) => (
            <label key={repo.id} className="gc-choice">
              <input
                type="checkbox"
                disabled={busy}
                checked={selected.includes(repo.id)}
                onChange={(event) =>
                  setSelected((ids) =>
                    event.target.checked
                      ? [...ids, repo.id]
                      : ids.filter((id) => id !== repo.id),
                  )
                }
              />
              <span>{repo.full_name}</span>
              {repo.private && (
                <span className="gc-muted gc-private">Private</span>
              )}
            </label>
          ))}
      </div>
      {!inventory.repositories.length && (
        <p className="gc-muted">
          No repositories are available to this account.
        </p>
      )}
      {!!inventory.repositories.length &&
        !inventory.repositories.some((repo) =>
          repo.full_name.toLowerCase().includes(query.toLowerCase()),
        ) && <p className="gc-muted">No repositories match your search.</p>}
      <div className="gc-footer">
        <Button variant="ghost" disabled={busy} onClick={cancel}>
          Cancel
        </Button>
        <Button
          disabled={busy || !selected.length}
          onClick={() => confirm(selected)}
        >
          Save access
        </Button>
      </div>
    </section>
  );
}
