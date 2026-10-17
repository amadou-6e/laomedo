import { useEffect, useState, type ReactNode } from "react";
import { useUpdateNodeInternals } from "@xyflow/react";

// Only scalar configuration controls belong here. Connected fields remain on
// the normal canvas path so collapsing this section never hides a wired port.
const CONTROLS = new Set([
  "output_retries", "timeout_seconds", "runner_url", "bridge_url",
  "request_id", "run_reference_json", "skill_id", "revision_id",
]);
export function advancedAgentFields(data: any, fields: string[], edges: any[], toolMode: boolean): string[] {
  const kind = data.node?.name || data.type;
  if (!["LaomedoCodexAgent", "LaomedoOpenCodeAgent"].includes(kind)) return [];
  return fields.filter((name) => {
    const field = data.node?.template?.[name];
    return CONTROLS.has(name) && field?.show && field.advanced === true && field.type !== "other" &&
      !(toolMode && field.tool_mode) && !edges.some((edge) =>
        edge.target === data.id && edge.data?.targetHandle?.fieldName === name);
  });
}

export default function AgentAdvancedControls({ nodeId, visible, children }: {
  nodeId: string; visible: boolean; children: ReactNode;
}) {
  const [expanded, setExpanded] = useState(false);
  const updateNodeInternals = useUpdateNodeInternals();
  useEffect(() => {
    const frame = requestAnimationFrame(() => updateNodeInternals(nodeId));
    return () => cancelAnimationFrame(frame);
  }, [expanded, visible, nodeId, updateNodeInternals]);
  const contentId = `agent-advanced-${nodeId}`;
  return <div hidden={!visible} className="nodrag nopan border-t" data-testid="agent-advanced-controls">
    <button type="button" className="flex w-full items-center gap-2 px-4 py-3 text-left text-xs font-medium hover:bg-muted"
      aria-expanded={expanded} aria-controls={contentId} onClick={() => setExpanded((value) => !value)}>
      <span aria-hidden="true">{expanded ? "▾" : "▸"}</span>Advanced controls
    </button>
    <div id={contentId} hidden={!expanded} className="nowheel">{children}</div>
  </div>;
}
