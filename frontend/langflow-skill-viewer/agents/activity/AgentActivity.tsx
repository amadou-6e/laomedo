import { useEffect, useState } from "react";
import { api } from "@/controllers/API/api";
import { getBaseUrl } from "@/customization/utils/urls";
import BaseModal from "@/modals/baseModal";
import { ToolbarButton } from "@/pages/FlowPage/components/nodeToolbarComponent/components/toolbar-button";

type Run = {id:string;provider:string;started:string;ended:string|null;status:string;stream_state:string;native_session:string|null;event_count:number;usage:Record<string,unknown>|null;reason:string|null};
type Receipt = {sequence:number;received_at:string;kind:string;raw:Record<string,unknown>};
type Page = {schema_version:string;run:Run;events:Receipt[];next_after:number;has_more:boolean};
export default function AgentActivity({flowId,nodeId}:{flowId:string;nodeId:string}) {
  const [open,setOpen]=useState(false);
  return <><ToolbarButton icon="Activity" label="Agent activity" onClick={()=>setOpen(true)} dataTestId="agent-activity-button" />
    {open && <AgentActivityModal flowId={flowId} nodeId={nodeId} open={open} setOpen={setOpen}/>}</>;
}
export function AgentActivityModal({flowId,nodeId,open,setOpen}:{flowId:string;nodeId:string;open:boolean;setOpen:(open:boolean)=>void}) {
  const [runs,setRuns]=useState<Run[]>([]);const [selected,setSelected]=useState("");
  const [page,setPage]=useState<Page|null>(null);const [error,setError]=useState("");
  const [loading,setLoading]=useState(true);const [reload,setReload]=useState(0);const [after,setAfter]=useState(0);
  const base=`${getBaseUrl()}laomedo/agent-activity/${encodeURIComponent(flowId)}/${encodeURIComponent(nodeId)}`;
  useEffect(()=>{setSelected("");setPage(null);setAfter(0)},[flowId,nodeId]);
  useEffect(()=>{
    const controller=new AbortController();setError("");setLoading(true);
    api.get<{schema_version:string;runs:Run[]}>(base,{signal:controller.signal}).then(({data})=>{
      if(controller.signal.aborted)return;
      if(data.schema_version!=="laomedo.agent-activity.v1")throw Error();
      setRuns(data.runs);setSelected(current=>data.runs.some(run=>run.id===current)?current:data.runs[0]?.id??"");
    }).catch(()=>{if(!controller.signal.aborted)setError("Activity unavailable. The host may not have capture configured.")})
      .finally(()=>{if(!controller.signal.aborted)setLoading(false)});
    return()=>controller.abort();
  },[base,reload]);
  useEffect(()=>{
    const controller=new AbortController();setPage(null);
    if(!selected)return()=>controller.abort();
    setLoading(true);setError("");
    api.get<Page>(`${base}/${encodeURIComponent(selected)}?after=${after}`,{signal:controller.signal}).then(({data})=>{
      if(controller.signal.aborted)return;
      if(data.schema_version!=="laomedo.agent-activity.v1"||data.run.id!==selected)throw Error();
      setPage(data);
    }).catch(()=>{if(!controller.signal.aborted)setError("This activity is unavailable or you do not have access.")})
      .finally(()=>{if(!controller.signal.aborted)setLoading(false)});
    return()=>controller.abort();
  },[base,selected,after,reload]);
  return <BaseModal open={open} setOpen={setOpen} size="large">
    <BaseModal.Header description="Inspect retained native agent activity. Viewing or refreshing never starts an agent."><span>Agent activity</span></BaseModal.Header>
    <BaseModal.Content>
      <div className="mb-4 flex gap-3"><label>Invocation <select aria-label="Invocation" className="rounded border bg-background p-2" value={selected} onChange={event=>{setSelected(event.target.value);setAfter(0)}}>
        {runs.map(run=><option key={run.id} value={run.id}>{run.started} · {run.status}</option>)}
      </select></label><button className="rounded border px-3" onClick={()=>setReload(value=>value+1)} disabled={loading}>Refresh activity</button></div>
      {loading&&<p role="status">Loading activity...</p>}{error&&<p role="alert">{error}</p>}
      {!loading&&!error&&runs.length===0&&<p>No retained activity for this agent. Capture must be enabled on the host before a run.</p>}
      {page&&page.run.id===selected&&<article data-testid="agent-activity-content" className="break-words">
        <dl className="mb-4 grid grid-cols-2 gap-2"><dt>Status</dt><dd>{page.run.status}</dd><dt>Captured stream</dt><dd>{page.run.stream_state}{page.run.reason?` (${page.run.reason})`:""}</dd>
          <dt>Provider</dt><dd>{page.run.provider}</dd><dt>Native session</dt><dd>{page.run.native_session??"Unknown"}</dd>
          <dt>Started</dt><dd>{page.run.started}</dd><dt>Ended</dt><dd>{page.run.ended??"Not observed"}</dd>
          <dt>Received events</dt><dd>{page.run.event_count} (unique actions uncertain)</dd><dt>Usage</dt><dd>{page.run.usage===null?"Unknown":JSON.stringify(page.run.usage)}</dd>
        </dl>
        <p className="mb-4 text-sm text-muted-foreground">Stream completeness describes captured evidence, not task success. Repeated receipts remain visible.</p>
        <ol className="space-y-3">{page.events.map(event=><li key={event.sequence} className="rounded border p-3">
          <div className="font-semibold">#{event.sequence} {event.kind}</div><p className="text-sm text-muted-foreground">{event.received_at} · Observed native event</p>
          <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap text-sm">{JSON.stringify(event.raw,null,2)}</pre>
        </li>)}</ol>
        <div className="mt-4 flex gap-3">{after>0&&<button className="rounded border p-2" onClick={()=>setAfter(0)}>First events</button>}
          {page.has_more&&<button className="rounded border p-2" onClick={()=>setAfter(page.next_after)}>Next events</button>}</div>
      </article>}
    </BaseModal.Content>
  </BaseModal>;
}
