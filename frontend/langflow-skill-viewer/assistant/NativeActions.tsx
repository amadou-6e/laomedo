import { useState } from "react";
import { assistantRequest } from "./api";
import type { NativeAction } from "./models";

export default function NativeActions({ conversation, provider = "codex", actions, onFailure }: {
  conversation: string; provider?: string; actions: NativeAction[]; onFailure: (error: unknown) => void;
}) {
  const [busy, setBusy] = useState<string>();
  const [observed, setObserved] = useState<Record<string, NativeAction>>({});
  async function decide(action: NativeAction, decision: "approve" | "reject") {
    if (busy) return;
    setBusy(action.id);
    try {
      const result = await assistantRequest<NativeAction>(
        `/conversations/${conversation}/native-actions/${action.id}/decision`,
        { decision, digest: action.digest },
      );
      setObserved(value => ({ ...value, [action.id]: result }));
    } catch (error) { onFailure(error); }
    finally { setBusy(undefined); }
  }
  if (!actions.length) return null;
  return <div className="space-y-3">{actions.map(proposal => {
    const action = proposal.state === "pending" ? observed[proposal.id] ?? proposal : proposal;
    const outcome = ({ completed: "Completed", rejected: "Rejected", expired: "Expired", stale: "Commands changed", executing: "Running", failed: "Failed", cancelled: "Stopped", interrupted: "Interrupted", unknown: "Outcome unknown" } as Record<string, string>)[action.state];
    return <article key={action.id} aria-label={`Native command: /${action.name}`}
      className={`rounded-lg border border-border/60 bg-transparent px-3 text-sm ${action.state === "pending" ? "py-3" : "py-2"}`}>
      <p className="whitespace-pre-wrap break-words text-xs font-normal text-muted-foreground">
        {action.state === "completed" ? "Ran" : "Run"} /{action.name}{action.arguments ? ` with arguments ${JSON.stringify(action.arguments)}` : ""}.
      </p>
      {outcome && <span role="status" className="mt-1 block text-left text-xs text-muted-foreground">{outcome}</span>}
      {action.state === "pending" && action.may_use_model && <p className="my-2 text-xs text-muted-foreground">May use model quota.</p>}
      {action.state === "pending" && provider === "opencode" && <p className="my-2 text-xs text-muted-foreground">Targets an isolated controller directory containing agent configuration, not your repository or the worker workspace.{action.name === "init" ? " AGENTS.md is retained only if written through the worker tool." : " No repository files or Git history are available there."}</p>}
      {action.state === "pending" && action.can_decide && <div className="mt-2 flex gap-2">
        <button type="button" className="rounded-md border px-2.5 py-1.5 text-xs hover:bg-muted disabled:opacity-50" disabled={Boolean(busy)} onClick={() => void decide(action, "approve")}>{busy === action.id ? "Checking..." : "Approve"}</button>
        <button type="button" className="rounded-md border px-2.5 py-1.5 text-xs hover:bg-muted disabled:opacity-50" disabled={Boolean(busy)} onClick={() => void decide(action, "reject")}>Reject</button>
      </div>}
      {action.state === "pending" && !action.can_decide && <p className="mt-1 text-xs text-muted-foreground">Approval unavailable in this app session.</p>}
    </article>;
  })}</div>;
}
