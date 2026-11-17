import { useState } from "react";
import { ExternalLink } from "lucide-react";
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
        const state =
          action.state === "pending" && action.expires_at * 1000 <= Date.now()
            ? "expired"
            : action.state;
        const outcome =
          state === "succeeded"
            ? category === "rename"
              ? "Renamed"
              : category === "run"
                ? "Completed"
                : "Edited"
            : state === "rejected"
              ? "Rejected"
              : state === "expired"
                ? "Expired"
                : state === "executing"
                  ? "Running"
                  : state === "unknown"
                    ? "Outcome unknown"
                    : state === "stale"
                      ? "Graph changed"
                      : state === "not_dispatched"
                        ? "Not started"
                        : state === "failed"
                          ? "Failed"
                          : action.can_decide === false
                            ? "Another app session"
                            : "";
        const explanation =
          state === "unknown"
            ? "Inspect run history before another run. Nothing is automatically retried."
            : state === "failed" &&
                action.error_code === "assistant_graph_name_conflict"
              ? "Another workflow has that name. No changes were saved."
              : state === "failed"
                ? "Earlier component effects may have occurred."
                : state === "executing"
                  ? "Chat Stop does not cancel this graph run."
                  : state === "not_dispatched"
                    ? "No graph execution started. Check your session and settings."
                    : state === "stale" ||
                        state === "expired" ||
                        action.can_decide === false
                      ? "Ask for a fresh proposal in this app session."
                      : undefined;
        return (
          <article
            key={action.id}
            aria-label={`${action.kind === "edit" ? "Edit" : "Run"} graph: ${action.name}`}
            className={`rounded-lg border border-border/60 bg-transparent px-3 text-sm ${pending ? "py-3" : "py-2"}`}
          >
            <div className="flex items-center justify-between gap-3">
              <h3 className="text-xs font-medium">
                {category === "rename"
                  ? "Rename"
                  : category === "run"
                    ? "Run"
                    : "Edit"}{" "}
                workflow
              </h3>
              <a
                className="shrink-0 rounded p-1 text-muted-foreground transition-colors hover:text-foreground focus-visible:outline focus-visible:outline-2"
                href={`/flow/${encodeURIComponent(action.workflow_id)}`}
                target="_blank"
                rel="noopener noreferrer"
                aria-label="Open workflow in new tab"
                title="Open workflow in new tab. Reload open editors before saving to avoid overwriting saved changes."
              >
                <ExternalLink size={14} aria-hidden="true" />
              </a>
            </div>
            <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-1">
              <div className="min-w-0 flex-1 text-xs font-normal text-muted-foreground">
                <p className="whitespace-pre-wrap break-words">
                  {category === "rename"
                    ? `“${action.name}” → “${action.new_name}”`
                    : `“${action.name}”`}
                </p>
                {category !== "rename" && action.summary && (
                  <p className="whitespace-pre-wrap break-words">
                    {action.summary}
                  </p>
                )}
                {category !== "rename" && !action.summary && (
                  <ul className="space-y-1 whitespace-pre-wrap break-words">
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
              </div>
              {outcome && (
                <span
                  role="status"
                  aria-live="polite"
                  title={explanation}
                  className="shrink-0 text-xs font-normal text-muted-foreground"
                >
                  {outcome}
                </span>
              )}
            </div>
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
              <div className="mt-2 flex flex-wrap gap-2">
                <button
                  type="button"
                  className="rounded-md border px-2.5 py-1.5 text-xs hover:bg-muted disabled:opacity-50"
                  disabled={Boolean(busy)}
                  onClick={() => void decide(action, "approve")}
                >
                  {busy === action.id ? "Checking..." : "Approve"}
                </button>
                <button
                  type="button"
                  className="rounded-md border px-2.5 py-1.5 text-xs hover:bg-muted disabled:opacity-50"
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
                  className="rounded-md border px-2.5 py-1.5 text-xs hover:bg-muted disabled:opacity-50"
                  disabled={Boolean(busy)}
                  onClick={() => void decide(action, "reject")}
                >
                  Reject
                </button>
              </div>
            )}
          </article>
        );
      })}
    </div>
  );
}
