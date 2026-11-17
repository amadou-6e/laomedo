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
  async function decide(
    action: GraphAction,
    decision: "approve" | "always_approve" | "reject",
  ) {
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
        const category = action.category ?? action.kind;
        const pending =
          action.state === "pending" &&
          action.expires_at * 1000 > Date.now() &&
          action.can_decide !== false;
        return (
          <article
            key={action.id}
            aria-label={`${action.kind === "edit" ? "Edit" : "Run"} graph: ${action.name}`}
            className="rounded-xl border bg-muted/30 p-4 text-sm"
          >
            <h3 className="font-semibold">
              {category === "rename"
                ? "Rename"
                : category === "run"
                  ? "Run"
                  : "Edit"}{" "}
              workflow
            </h3>
            <p className="my-2 whitespace-pre-wrap break-words">
              {category === "rename"
                ? `“${action.name}” → “${action.new_name}”`
                : `“${action.name}”`}
            </p>
            {category !== "rename" && action.summary && (
              <p className="my-2 whitespace-pre-wrap break-words">
                {action.summary}
              </p>
            )}
            {category !== "rename" && !action.summary && (
              <ul className="my-2 space-y-1 whitespace-pre-wrap break-words">
                {action.preview
                  .filter(
                    (line) =>
                      !line.startsWith("Reload open editor") &&
                      !line.startsWith("Runs as your") &&
                      !line.startsWith("May consume"),
                  )
                  .map((line, index) => (
                    <li key={index}>{line}</li>
                  ))}
              </ul>
            )}
            {category === "run" && pending && (
              <p className="my-2 text-xs text-muted-foreground">
                Uses configured credentials; may incur costs or perform external
                actions.
              </p>
            )}
            {pending && (
              <p className="mb-2 text-xs text-muted-foreground">
                Always: any graph in this conversation.
              </p>
            )}
            {pending && (
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  className="rounded-md border bg-primary px-3 py-2 text-primary-foreground disabled:opacity-50"
                  disabled={Boolean(busy)}
                  onClick={() => void decide(action, "approve")}
                >
                  {busy === action.id ? "Checking..." : "Approve"}
                </button>
                <button
                  type="button"
                  className="rounded-md border px-3 py-2 disabled:opacity-50"
                  disabled={Boolean(busy)}
                  title="For any graph in this conversation, while signed in with this app session"
                  onClick={() => void decide(action, "always_approve")}
                >
                  Always approve{" "}
                  {category === "rename"
                    ? "renames"
                    : category === "run"
                      ? "runs"
                      : "edits"}
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
              {action.state === "pending" && action.can_decide === false
                ? "This proposal belongs to another app session. Ask for a fresh proposal here."
                : action.state === "executing"
                  ? "Graph running. Chat Stop does not cancel this run."
                  : action.state === "unknown"
                    ? "Outcome uncertain. Inspect run history before proposing another run; nothing will be automatically retried."
                    : action.state === "stale"
                      ? "The saved graph changed. Ask for a fresh proposal."
                      : action.state === "not_dispatched"
                        ? "The graph was not started. Check your session and run settings before requesting a fresh proposal."
                        : action.state === "failed"
                          ? action.error_code ===
                            "assistant_graph_name_conflict"
                            ? "Another graph already has that name. No changes were saved; ask for a fresh proposal."
                            : "The graph run failed; earlier component effects may have occurred."
                          : action.state === "succeeded"
                            ? action.kind === "edit"
                              ? "Saved graph updated."
                              : "Graph run completed."
                            : action.state === "rejected"
                              ? "Rejected. No action was executed."
                              : pending
                                ? ""
                                : "This proposal is no longer available for approval."}
            </p>
            <details className="mt-2 text-xs text-muted-foreground">
              <summary className="cursor-pointer">Details</summary>
              <ul className="my-2 space-y-1 whitespace-pre-wrap break-words">
                {action.preview.map((line, index) => (
                  <li key={index}>{line}</li>
                ))}
              </ul>
              <p>Saved revision: {action.revision}</p>
              <p>
                Proposal: {action.id} ? {action.state}
              </p>
              <p>
                Expires: {new Date(action.expires_at * 1000).toLocaleString()}
              </p>
              {action.run_id && (
                <p className="break-all">Run ID: {action.run_id}</p>
              )}
            </details>
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
