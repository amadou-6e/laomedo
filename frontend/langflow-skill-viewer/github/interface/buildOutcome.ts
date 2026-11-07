import { describeNodeFailure, hasLaomedoFailure, type NodeFailure } from "@/components/laomedoErrors/nodeErrors";
import type { VertexBuildTypeAPI } from "@/types/api";
import { nodeKind } from "../issues/selection";
import type { GitHubBuildState } from "../models";

/** A completed component build can still contain a failed or uncertain operation. */
export function githubBuildFailure(entry: VertexBuildTypeAPI, nodeType?: string): NodeFailure | undefined {
  if (!["LaomedoGitHubIssue", "LaomedoGitHubPR"].includes(nodeKind(nodeType ?? ""))) return;
  if (hasLaomedoFailure(entry)) return describeNodeFailure(undefined, entry);
}

/** Ignore prior runs and untouched nodes when summarizing the current execution. */
export function githubRunFailure(state: GitHubBuildState, touched: Set<string>, runId: string): NodeFailure | undefined {
  for (const node of state.nodes) {
    if (!touched.has(node.id)) continue;
    const entries = state.flowPool[node.id] ?? [];
    const entry = entries[entries.length - 1];
    if (!entry || entry.run_id !== runId) continue;
    const failure = githubBuildFailure(entry, node.data?.type);
    if (failure) return failure;
  }
}
