import { useState } from "react";
import { Button } from "@/components/ui/button";
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
  const inventory = attempt.inventory;
  if (!inventory) return null;
  return (
    <section className="grid gap-3 rounded border p-4">
      <h2 className="font-semibold">Confirm read access</h2>
      <p>Verified GitHub account: {inventory.principal.login}</p>
      <p>
        Select repositories whose contents Laomedo may read. This grants no
        Agent run or write permission.
      </p>
      {inventory.repositories.length === 0 && (
        <p>
          No repositories are available to this account and app. No read consent
          has been granted.
        </p>
      )}
      {inventory.repositories.map((repository) => (
        <label key={repository.id} className="flex gap-2 break-all">
          <input
            type="checkbox"
            disabled={busy}
            checked={selected.includes(repository.id)}
            onChange={(event) =>
              setSelected((ids) =>
                event.target.checked
                  ? [...ids, repository.id]
                  : ids.filter((id) => id !== repository.id),
              )
            }
          />
          {repository.full_name}
          {repository.private ? " (private)" : ""}
        </label>
      ))}
      <div className="flex flex-wrap gap-2">
        <Button
          disabled={busy || !selected.length}
          onClick={() => confirm(selected)}
        >
          Confirm selected reads
        </Button>
        <Button variant="outline" disabled={busy} onClick={cancel}>
          Cancel sign-in
        </Button>
      </div>
    </section>
  );
}
