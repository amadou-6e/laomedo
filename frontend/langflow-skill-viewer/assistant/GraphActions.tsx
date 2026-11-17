import { useState } from "react";
import { assistantRequest } from "./api";
import type { GraphAction } from "./models";

export default function GraphActions({
  conversation,
  actions,
  onFailure,
}: {
  conversation: string;
  actions: GraphAction[];
  onFailure: (error: unknown) => void;
}) {
  const [busy, setBusy] = useState<string>();
  const [observed, setObserved] = useState<Record<string, GraphAction>>({});
  async function decide(action: GraphAction, decision: "approve" | "reject") {
    if (busy) return;
    setBusy(action.id);
    try {
      const result = await assistantRequest<GraphAction>(
        `/conversations/${conversation}/actions/${action.id}/decision`,
        { decision, digest: action.digest },
      );
      setObserved((value) => ({ ...value, [action.id]: result }));
    } catch (error) {
      onFailure(error);
    } finally {
      setBusy(undefined);
    }
  }
  return (
    <div className="space-y-3">
      {actions.map((proposal) => {
        const action =
          proposal.state === "pending"
            ? (observed[proposal.id] ?? proposal)
            : proposal;
        const pending =
          action.state === "pending" && action.expires_at * 1000 > Date.now();
        return (
          <article
            key={action.id}
            aria-label={`${action.kind === "edit" ? "Edit" : "Run"} graph: ${action.name}`}
            className="rounded-xl border bg-muted/30 p-4 text-sm"
          >
            <h3 className="font-semibold">
              {action.kind === "edit" ? "Edit" : "Run"} graph: {action.name}
            </h3>
            <p className="mt-1 text-xs text-muted-foreground">
              Saved revision {action.revision.slice(7, 19)} ·{" "}
              {action.state === "pending" && !pending
                ? "expired"
                : action.state}
            </p>
            <ul className="my-3 space-y-2 whitespace-pre-wrap break-words">
              {action.preview.map((line, index) => (
                <li key={index}>{line}</li>
              ))}
            </ul>
            {pending && (
              <div className="flex gap-2">
                <button
                  type="button"
                  className="rounded-md border bg-primary px-3 py-2 text-primary-foreground disabled:opacity-50"
                  disabled={Boolean(busy)}
                  onClick={() => void decide(action, "approve")}
                >
                  {busy === action.id
                    ? "Checking…"
                    : action.kind === "edit"
                      ? "Approve changes"
                      : "Approve run"}
                </button>
                <button
                  type="button"
                  className="rounded-md border px-3 py-2 disabled:opacity-50"
                  disabled={Boolean(busy)}
                  onClick={() => void decide(action, "reject")}
                >
                  Reject
                </button>
              </div>
            )}
            <p
              role="status"
              aria-live="polite"
              className="mt-2 text-muted-foreground"
            >
              {action.state === "executing"
                ? "Graph running. Chat Stop does not cancel this run."
                : action.state === "unknown"
                  ? "Outcome uncertain. Inspect run history before proposing another run; nothing will be automatically retried."
                  : action.state === "stale"
                    ? "The saved graph changed. Ask for a fresh proposal."
                    : action.state === "failed"
                      ? "The graph run failed; earlier component effects may have occurred."
                      : action.state === "succeeded"
                        ? action.kind === "edit"
                          ? "Saved graph updated."
                          : "Graph run completed."
                        : action.state === "rejected"
                          ? "Rejected. No action was executed."
                          : pending
                            ? "Only the exact revision and request above will be approved."
                            : "This proposal is no longer available for approval."}
            </p>
            {action.run_id && (
              <p className="mt-2 break-all text-xs text-muted-foreground">
                Run ID: {action.run_id}
              </p>
            )}
            {action.state === "succeeded" && action.kind === "edit" && (
              <a
                className="mt-3 inline-block underline"
                href={`/flow/${encodeURIComponent(action.workflow_id)}`}
                target="_blank"
                rel="noopener noreferrer"
              >
                Open graph in new tab ↗
              </a>
            )}
          </article>
        );
      })}
    </div>
  );
}
