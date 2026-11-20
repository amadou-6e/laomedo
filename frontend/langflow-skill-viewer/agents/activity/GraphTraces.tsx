import { useState } from "react";
import GraphAgents from "./GraphAgents";
import { FlowInsightsContent } from "@/pages/FlowPage/components/TraceComponent/FlowInsightsContent";

export default function GraphTraces({ flowId }: { flowId?: string }) {
  const [view, setView] = useState("agents");
  return <section className="flex h-full min-w-0 flex-1 flex-col overflow-hidden" aria-label="Combined graph traces">
    <div role="tablist" aria-label="Trace view" className="flex shrink-0 gap-4 border-b px-4">{[{ id: "agents", label: "Agent activity" }, { id: "flow", label: "Flow execution" }].map(item => <button type="button" role="tab" aria-selected={view === item.id} aria-controls="trace-view" id={`trace-${item.id}`} key={item.id} onClick={() => setView(item.id)} className={`border-b-2 px-2 py-3 text-sm ${view === item.id ? "border-primary font-semibold" : "border-transparent text-muted-foreground"}`}>{item.label}</button>)}</div>
    <div id="trace-view" role="tabpanel" aria-labelledby={`trace-${view}`} className="flex min-h-0 flex-1 flex-col">{view === "agents" ? <GraphAgents flowId={flowId} /> : <FlowInsightsContent flowId={flowId} refreshOnMount showFlowActivityHeader />}</div>
  </section>;
}
