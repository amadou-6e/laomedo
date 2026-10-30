import CopyIcon from "@/components/laomedoErrors/CopyIcon";
import ErrorExplanation, { formatErrorCopy } from "@/components/laomedoErrors/ErrorExplanation";
import { describeNodeFailure, type NodeFailure } from "@/components/laomedoErrors/nodeErrors";

const refusals = new Set(["invalid_skill_id", "immutable_skill_revision_required", "skill_revision_unavailable", "skill_revision_unsafe", "skill_revision_too_large"]);
const readFailures = new Set(["skill_inspection_unavailable", "skill_history_unavailable", "skill_comparison_unavailable"]);

export function describeInspectionFailure(raw: unknown, fallback = "skill_inspection_unavailable"): NodeFailure {
  // Langflow's 404 handler unwraps detail; standalone FastAPI retains it. Read
  // only those declared code slots, never stringify response bodies or traces.
  const data = (raw as { response?: { data?: { code?: unknown; detail?: { code?: unknown } } } })?.response?.data;
  const code = data?.code ?? data?.detail?.code;
  const failure = describeNodeFailure(code ?? fallback, undefined);
  return refusals.has(failure.diagnostics.code) || readFailures.has(failure.diagnostics.code)
    ? failure : { ...describeNodeFailure(fallback, undefined), diagnostics: failure.diagnostics };
}

export default function SkillInspectionError({ failure, onReload, reloadLabel }: {
  failure: NodeFailure; onReload: () => void; reloadLabel: "Reload files" | "Reload history";
}) {
  return <div role="alert" className="p-2 text-sm">
    <div className="flex items-start justify-between gap-2"><h3 className="py-1 font-semibold">{failure.title}</h3><CopyIcon text={formatErrorCopy(failure)} /></div>
    <ErrorExplanation failure={failure} />
    {!refusals.has(failure.diagnostics.code) && <button type="button" className="mt-2 rounded border px-3 py-1" onClick={onReload}>{reloadLabel}</button>}
  </div>;
}
