import { useState } from "react";
import { assistantRequest } from "./api";

export default function GraphPermissions({
  conversation,
  permissions,
  onChange,
  onFailure,
}: {
  conversation: string;
  permissions: ("rename" | "edit" | "run")[];
  onChange: () => void;
  onFailure: (error: unknown) => void;
}) {
  const [busy, setBusy] = useState(false);
  async function revoke(category: string) {
    if (busy) return;
    setBusy(true);
    try {
      await assistantRequest(
        `/conversations/${conversation}/permissions/${category}/revoke`,
        {},
      );
      onChange();
    } catch (error) {
      onFailure(error);
    } finally {
      setBusy(false);
    }
  }
  if (!permissions.length) return null;
  return (
    <aside
      aria-label="Conversation approvals"
      className="rounded-lg border p-3 text-xs text-muted-foreground"
    >
      {permissions.map((category) => (
        <div
          key={category}
          className="flex flex-wrap items-center justify-between gap-2 py-1"
        >
          <span>
            Always approve{" "}
            {category === "rename"
              ? "renames"
              : category === "run"
                ? "runs"
                : "edits"}{" "}
            in this conversation
          </span>
          <button
            type="button"
            disabled={busy}
            className="underline disabled:opacity-50"
            onClick={() => void revoke(category)}
          >
            Ask every time<span className="sr-only"> for {category}</span>
          </button>
        </div>
      ))}
    </aside>
  );
}
