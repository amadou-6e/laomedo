import { useEffect, useId, useState } from "react";
import { api } from "@/controllers/API/api";
import { getBaseUrl } from "@/customization/utils/urls";
import BaseModal from "@/modals/baseModal";
import useFlowStore from "@/stores/flowStore";

const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const tabs = ["Overview", "Output validation", "Timeline"];
const shown = (value: unknown) => value === null || value === undefined ? "Unknown" : typeof value === "boolean" ? value ? "Yes" : "No" : String(value);
function nodeRun(entries: any) {
  const entry = Array.isArray(entries) ? entries[entries.length - 1] : null;
  const outputs = entry?.data?.outputs;
  const candidates = [outputs?.run?.message, outputs?.submission?.message?.run_reference, entry?.artifacts?.run?.raw, entry?.artifacts?.submission?.raw?.run_reference];
  return candidates.find(value => typeof value?.run_id === "string" && uuid.test(value.run_id))?.run_id ?? "";
}
export default function AgentInspectionModal({open, setOpen, template, nodeId}: {open: boolean; setOpen: (v:boolean)=>void; template: any; nodeId: string}) {
  const id = useId();
  const pool = useFlowStore(state => state.flowPool[nodeId]);
  const current = nodeRun(pool);
  const runner = typeof template?.runner_url?.value === "string" ? template.runner_url.value : "";
  const [selected,setSelected] = useState(""); const [runs,setRuns] = useState<any[]>([]);
  const [snapshot,setSnapshot] = useState<any>(null); const [tab,setTab] = useState(0);
  const [loading,setLoading] = useState(false); const [error,setError] = useState(""); const [reload,setReload] = useState(0);
  const [after,setAfter] = useState(0); const [pages,setPages] = useState<number[]>([0]);
  useEffect(() => {
    const abort = new AbortController(); setSelected(current); setRuns([]); setSnapshot(null); setAfter(0); setPages([0]); setTab(0); setError("");
    if (!open) return () => abort.abort();
    api.post(`${getBaseUrl()}laomedo/agents/history`, {runner_url:runner}, {signal:abort.signal}).then(({data}) => {
      if (!abort.signal.aborted) { if (data.schema_version !== "laomedo.agent-history.v1" || !Array.isArray(data.runs)) throw Error(); setRuns(data.runs.filter((r:any) => typeof r.run_id === "string" && uuid.test(r.run_id))); }
    }).catch(() => {if (!abort.signal.aborted) setError("Run history unavailable. Check the configured inspection connection.");});
    return () => abort.abort();
  }, [open,nodeId,runner,current]);
  useEffect(() => {
    const abort = new AbortController();setSnapshot(null);setLoading(false);
    if (!open || !uuid.test(selected)) return () => abort.abort();
    setError("");setLoading(true);
    api.post(`${getBaseUrl()}laomedo/agents/inspect`, {runner_url:runner,run_id:selected,after}, {signal:abort.signal}).then(({data}) => {
      if (!abort.signal.aborted) {if (data.schema_version !== "laomedo.agent-inspection.v1" || data.summary?.run_id !== selected || !Array.isArray(data.events)) throw Error();setSnapshot(data);}
    }).catch(() => {if (!abort.signal.aborted) setError("Inspection unavailable. No run was started or retried.");}).finally(() => {if (!abort.signal.aborted) setLoading(false);});
    return () => abort.abort();
  }, [open,nodeId,runner,selected,after,reload]);
  const summary = snapshot?.summary;
  const chooseTab = (index:number) => {setTab(index);document.getElementById(id+"-tab-"+index)?.focus();};
  return <BaseModal open={open} setOpen={setOpen} size="large">
    <BaseModal.Header description="Read-only recorded evidence. Inspection never runs, retries or cancels an agent."><span>Inspect agent</span></BaseModal.Header>
    <BaseModal.Content className="min-h-0 gap-4">
      <label className="flex flex-col gap-2 text-sm">Recorded run
        <select data-testid="agent-run-select" className="rounded border bg-background p-2 font-mono text-sm" value={selected} onChange={e => {setSelected(e.target.value);setAfter(0);setPages([0]);}}>
          <option value="">Select a recorded run</option>
          {current && !runs.some(r=>r.run_id===current) && <option value={current}>{current} (node output)</option>}
          {runs.map(r => <option key={r.run_id} value={r.run_id}>{r.run_id} ({r.status})</option>)}
        </select>
      </label>
      <p className="text-sm text-muted-foreground">{selected && selected===current ? "Bound to this node's current output." : "Runner history: manually selected records are not attested as this node's invocation."}</p>
      <div role="tablist" aria-label="Agent inspection" className="flex gap-2 border-b pb-2">
        {tabs.map((name,index)=><button key={name} id={id+"-tab-"+index} role="tab" aria-selected={tab===index} aria-controls={id+"-panel"} tabIndex={tab===index?0:-1} className={"rounded px-3 py-2 text-sm "+(tab===index?"bg-secondary font-semibold":"")} onClick={()=>setTab(index)} onKeyDown={e=>{if(["ArrowLeft","ArrowRight","Home","End"].includes(e.key)){e.preventDefault();chooseTab(e.key==="Home"?0:e.key==="End"?2:(tab+(e.key==="ArrowRight"?1:2))%3);}}}>{name}</button>)}
      </div>
      {loading && <p role="status">Loading recorded evidence...</p>}
      {error && <p role="alert">{error}</p>}
      {!selected && <p>Select a run to inspect. No latest run is guessed.</p>}
      {summary && <section role="tabpanel" id={id+"-panel"} aria-labelledby={id+"-tab-"+tab} data-testid="agent-inspection-content">
        {tab===0 && <dl className="grid grid-cols-1 gap-3 text-sm sm:grid-cols-2">
          {[["Run ID",summary.run_id],["Thread",summary.thread_id],["Execution",summary.executor_status],["Task outcome",summary.task_outcome],["Evidence complete",summary.evidence_complete],["Completion basis",summary.completion_basis],["Requested model",summary.requested_model],["Reported model",summary.effective_model],["Requested effort",summary.requested_effort],["Reported effort",summary.effective_effort],["Campaign turns used / cap",summary.budget?.used==null?null:shown(summary.budget.used)+" / "+shown(summary.budget.cap)],["Turns remaining",summary.budget?.remaining],["Input tokens",summary.usage?.input_tokens],["Output tokens",summary.usage?.output_tokens],["Cached input tokens",summary.usage?.cached_input_tokens],["Error category",summary.error_category]].map(([key,value])=><div key={String(key)}><dt className="text-muted-foreground">{String(key)}</dt><dd className="break-all font-mono">{shown(value)}</dd></div>)}
          <p className="text-muted-foreground sm:col-span-2">Execution completion is separate from task success and Contract acceptance. Missing usage is unknown, not zero. Subscription usage is not an API charge.</p>
        </dl>}
        {tab===1 && <div className="space-y-3 text-sm">
          <p>Contract: <strong>{summary.output_validation?.contract_status ?? "Unknown"}</strong></p>
          {summary.output_syntax && <p role="status">Invalid JSON ({summary.output_syntax.reason}) at line {summary.output_syntax.line}, column {summary.output_syntax.column}.</p>}
          <ul className="space-y-2">{summary.output_validation?.errors?.map((e:any,index:number)=><li key={index}><code>{e.path || "/"}: {e.code}</code></li>)}</ul>
          <p>Precheck installed: {shown(summary.precheck?.installed)}; calls: {shown(summary.precheck?.call_count)}</p>
          <p>Output retries: {shown(summary.output_retries)}; corrections: {shown(summary.output_correction_count)}</p>
          <p>Correction blocked: {shown(summary.output_correction_blocked)}</p>
          <p className="text-muted-foreground">Precheck acceptance does not establish that the final answer was valid. This panel does not publish or repeat operations.</p>
        </div>}
        {tab===2 && <div className="space-y-3 text-sm">
          <p className="text-muted-foreground">Metadata only. Message content, command arguments and tool results are withheld. Durations are shown only when reported.</p>
          <ol className="space-y-2">{snapshot.events.map((event:any)=><li key={event.sequence} className="rounded border p-3"><div className="font-mono">#{event.sequence} {event.event_type} / {event.item_type}</div><div>Item {shown(event.item_id)}; turn {shown(event.turn_id)}</div>{event.tool && <div>Tool: {event.tool}</div>}{event.exit_code!=null && <div>Exit: {event.exit_code}</div>}{event.duration_ms!=null && <div>Duration: {event.duration_ms} ms</div>}</li>)}</ol>
          {!snapshot.events.length && <p>No projected events on this page.</p>}
          <p>Trace read: {snapshot.trace_status}</p>
          <div className="flex gap-3"><button disabled={pages.length<2} onClick={()=>{const prev=pages.slice(0,-1);setPages(prev);setAfter(prev[prev.length-1]);}}>Previous page</button><button disabled={snapshot.next_cursor==null} onClick={()=>{setAfter(snapshot.next_cursor);setPages([...pages,snapshot.next_cursor]);}}>Next page</button></div>
        </div>}
      </section>}
    </BaseModal.Content>
    <BaseModal.Footer><button className="rounded border px-3 py-2 text-sm" disabled={loading || !selected} onClick={()=>setReload(v=>v+1)}>Refresh evidence</button></BaseModal.Footer>
  </BaseModal>;
}
