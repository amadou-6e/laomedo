import ConnectionNavigation from "./ConnectionNavigation";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { PendingConnection } from "./types";

export default function ConnectionInventory({
  attempt,
  busy,
  confirm,
  cancel,
  initialRepositoryIds = [],
  manageAccess,
  refresh,
}: {
  attempt: PendingConnection;
  busy: boolean;
  confirm: (ids: number[]) => void;
  cancel: () => void;
  initialRepositoryIds?: number[];
  manageAccess?: string;
  refresh?: () => void;
}) {
  const [selected, setSelected] = useState<number[]>(() =>
    initialRepositoryIds.filter((id) =>
      attempt.inventory?.repositories.some((repo) => repo.id === id),
    ),
  );
  const [query, setQuery] = useState("");
  const inventory = attempt.inventory;
  if (!inventory) return null;
  const availableSelection = selected.filter((id) =>
    inventory.repositories.some((repo) => repo.id === id),
  );
  return (
    <div className="gc-screen gc-consent">
      <section className="gc-panel gc-consent">
        <h2>Choose repositories</h2>
        <p className="gc-muted">
          Choose what Laomedo may read. You can change this later. Only
          repositories this connection can access are shown.
        </p>
        <div className="gc-identity">
          <span className="gc-avatar" aria-hidden="true">
            {inventory.principal.login[0]?.toUpperCase()}
          </span>
          <strong>@{inventory.principal.login}</strong>
        </div>
        {inventory.repositories.length > 5 && (
          <Input
            aria-label="Search repositories"
            placeholder="Search repositories"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        )}
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
                  checked={availableSelection.includes(repo.id)}
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
        {manageAccess && (
          <a className="gc-link" href={manageAccess}>
            {inventory.repositories.length
              ? "Manage repository access on GitHub"
              : "Choose repositories on GitHub"}
          </a>
        )}
        <div className="gc-footer">
          <Button
            ignoreTitleCase
            disabled={busy || !availableSelection.length}
            onClick={() => confirm(availableSelection)}
          >
            Save access
          </Button>
        </div>
      </section>
      <ConnectionNavigation busy={busy} back={cancel} refresh={refresh} />
    </div>
  );
}
