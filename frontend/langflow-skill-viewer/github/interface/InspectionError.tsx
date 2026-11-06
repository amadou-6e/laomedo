import CopyIcon from "@/components/laomedoErrors/CopyIcon";
import ErrorExplanation, { formatErrorCopy } from "@/components/laomedoErrors/ErrorExplanation";
import { describeNodeFailure, isKnownNodeError, type NodeFailure } from "@/components/laomedoErrors/nodeErrors";

export function describeGitHubInspectionFailure(raw: unknown, kind: "issue" | "pr"): NodeFailure {
  const data = (raw as { response?: { data?: { code?: unknown; detail?: { code?: unknown } } } })?.response?.data;
  const code = data?.code ?? data?.detail?.code;
  const failure = describeNodeFailure(code, undefined);
  const fallback = describeNodeFailure(kind === "issue" ? "github_issue_inspection_unavailable" : "github_pr_inspection_unavailable", undefined);
  if (isKnownNodeError(code, true) && code !== "github_issue_unavailable" && code !== "github_pr_unavailable") return failure;
  return { ...fallback, diagnostics: code === undefined ? fallback.diagnostics : failure.diagnostics };
}

export default function GitHubInspectionError({ failure }: { failure: NodeFailure }) {
  return <section role="alert" className="rounded border p-3 text-sm">
    <div className="flex items-start justify-between gap-2"><h3 className="py-1 font-semibold">{failure.title}</h3><CopyIcon text={formatErrorCopy(failure)} /></div>
    <ErrorExplanation failure={failure} />
  </section>;
}
