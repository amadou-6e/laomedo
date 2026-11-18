import { useEffect, useMemo, useState } from "react";
import { ChevronDown } from "lucide-react";
import { ActivityTimeline } from "./ActivityTimeline";
import { ProviderIcon } from "./ProviderIcon";
import NodeErrorNotice from "@/components/laomedoErrors/NodeErrorNotice";
import { describeNodeFailure } from "@/components/laomedoErrors/nodeErrors";
import IconComponent from "@/components/common/genericIconComponent";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useAgentActivityStore } from "@/stores/agentActivityStore";
import useFlowStore from "@/stores/flowStore";
import { api } from "@/controllers/API/api";
import { getBaseUrl } from "@/customization/utils/urls";
import type { Run, Detail, ExportContext, ActivityScope } from "./models";
import { time, duration, conversationRows, scopedProjection } from "./utils";
import { ActivityInfo } from "./components";
import { Conversation } from "./conversation";
import { UsageCharts } from "./usage";
import { RuntimeRecords } from "./telemetry";

export default function GraphAgents({flowId}:{flowId?:string}) {
  const nodes=useFlowStore(state=>state.nodes);
  const target=useAgentActivityStore(state=>state.target);
  const targetNode=target&&target.flowId===flowId?target.nodeId:undefined;
  useEffect(()=>()=>useAgentActivityStore.getState().clearTarget(),[]);
  useEffect(()=>{setExecution("");setSelected("")},[targetNode]);
  const label=(run:Run)=>run.node_label?.trim()||nodes.find(node=>node.id===run.node)?.data.node?.display_name||run.node;
  const statusBadge=(status:string)=><Badge size="tag" variant={status==="completed"?"successStatic":status==="running"||status==="waiting"?"secondaryStatic":"errorStatic"}>{status==="waiting"?"starting":status}</Badge>;
  const [runs,setRuns]=useState<Run[]>([]),[execution,setExecution]=useState("");
  const [details,setDetails]=useState<Record<string,Detail>>({}),[selected,setSelected]=useState("");
  const [scope,setScope]=useState<ActivityScope>({});
  const [error,setError]=useState(""),[refresh,setRefresh]=useState(0);
  const base=`${getBaseUrl()}laomedo/agent-executions/${encodeURIComponent(flowId??"")}`;
  useEffect(()=>{setRuns([]);setExecution("");setDetails({});setSelected("")},[flowId]);
  useEffect(()=>{setDetails({});setScope({})},[execution]);
  useEffect(()=>setScope({}),[flowId,targetNode]);
  useEffect(()=>{
    if(!flowId)return;
    const controller=new AbortController();
    let loading=false;
    const load=async()=>{
      if(loading||controller.signal.aborted)return;
      loading=true;
      try {
        const {data}=await api.get<{runs:Run[]}>(base,{signal:controller.signal});
        if(controller.signal.aborted)return;
        setRuns(data.runs);setError("");
        setExecution(current=>data.runs.some(run=>run.execution===current)?current:[...data.runs].filter(run=>run.execution&&(!targetNode||run.node===targetNode)).sort((a,b)=>b.started.localeCompare(a.started))[0]?.execution??data.runs.find(run=>run.execution)?.execution??"");
      } catch {if(!controller.signal.aborted)setError("Activity unavailable. Enable capture on the app host before running the graph.")}
      finally {loading=false}
    };
    void load();const timer=setInterval(load,2000);
    return()=>{controller.abort();clearInterval(timer)};
  },[base,flowId,refresh,targetNode]);
  const visible=runs.filter(run=>run.execution===execution).sort((a,b)=>a.started.localeCompare(b.started));
  const invocationIds=visible.map(run=>run.id).join(",");
  const live=visible.some(run=>run.status==="running");
  useEffect(()=>{
    setSelected(current=>visible.some(run=>run.id===current)?current:targetNode?[...visible].filter(run=>run.node===targetNode).sort((a,b)=>b.started.localeCompare(a.started))[0]?.id??"":visible[0]?.id??"");
  },[targetNode,execution,invocationIds]);
  useEffect(()=>{
    const controller=new AbortController();
    let inFlight=false;
    const load=async()=>{
      if(inFlight||controller.signal.aborted)return;
      inFlight=true;
      const queue=[...visible];
      try {
        const results=await Promise.allSettled(Array.from({length:Math.min(4,queue.length)},async()=>{
          while(queue.length&&!controller.signal.aborted){
            const run=queue.shift()!;
            const {data}=await api.get<Detail>(`${base}/${encodeURIComponent(run.node)}/${run.id}`,{signal:controller.signal});
            if(!controller.signal.aborted)setDetails(current=>({...current,[run.id]:data}));
          }
        }));
        if(results.some(result=>result.status==="rejected"))throw Error("activity_detail_unavailable");
      } catch {if(!controller.signal.aborted)setError("Some invocation details could not be loaded.")}
      finally {inFlight=false}
    };
    void load();const timer=live?setInterval(load,2000):null;
    return()=>{controller.abort();if(timer!==null)clearInterval(timer)};
  },[base,execution,invocationIds,live,refresh]);
  const start=Math.min(...visible.map(run=>Date.parse(run.started)));
  const end=Math.max(...visible.map(run=>Date.parse(run.ended??new Date().toISOString())));
  const detail=details[selected];
  const rowsByRun=useMemo(()=>Object.fromEntries(Object.entries(details).map(([id,value])=>[id,conversationRows(value.projection,value.run.native_session)])),[details]);
  const conversations=rowsByRun[selected]??[];
  const currentConversation=conversations.find(thread=>thread.id===scope.thread);
  const currentTurn=currentConversation?.turns.find(turn=>turn.id===scope.turn);
  const projection=useMemo(()=>detail?scopedProjection(detail.projection,scope):undefined,[detail,scope]);
  const breadcrumbs:typeof conversations=[];
  let ancestor=currentConversation;
  while(ancestor&&!breadcrumbs.some(value=>value.id===ancestor!.id)) {breadcrumbs.unshift(ancestor);ancestor=conversations.find(value=>value.id===ancestor!.parent)}
  const selectScope=(invocation:string,next:ActivityScope={})=>{setSelected(invocation);setScope(next)};
  const scopeLabel=scope.turn?"Turn":scope.thread?"Conversation":"Run";
  const exportContext:ExportContext|undefined=detail?{graph_id:flowId,run_id:detail.run.id,execution_id:detail.run.execution,node_id:detail.run.node,provider:detail.run.provider,model:(scope.thread&&scope.thread!==detail.run.native_session?projection?.cost.model:detail.run.model)??null,native_session:detail.run.native_session,scope,capture_state:detail.run.stream_state,capture_reason:detail.run.reason??null,truncated:detail.truncated}:undefined;
  const selectedLane=currentTurn??currentConversation?.lane??detail?.run;
  const executions=[...new Set(runs.map(run=>run.execution).filter((value):value is string=>Boolean(value)))];
  return <section className="flex h-full min-w-0 flex-1 flex-col overflow-hidden bg-background text-foreground" aria-label="Graph agent activity">
    <header className="flex min-h-12 shrink-0 items-center justify-between gap-3 border-b px-4 py-3"><h1 className="text-sm font-semibold">Agents</h1>
      <Button variant="ghost" size="icon" aria-label="Refresh" onClick={()=>setRefresh(value=>value+1)}><IconComponent name="RefreshCcw" className="h-4 w-4"/></Button></header>
    <div className="min-h-0 min-w-0 flex-1 overflow-y-auto overflow-x-hidden">
    <div className="flex min-h-full flex-col">
    <div className="flex min-w-0 flex-1 flex-col p-4">
    <section className="mb-12 overflow-hidden rounded-lg border border-border bg-muted/10" aria-label="Selected graph execution">
      <header className="flex flex-wrap items-center justify-between gap-4 border-b bg-muted/30 px-5 py-4">
        <label className="block min-w-0 max-w-full text-base font-semibold">Graph execution
          <span className="relative mt-2 block w-[420px] max-w-full">
            <select className="w-full appearance-none rounded-md border border-border bg-background/50 py-2.5 pl-3 pr-9 text-xs font-normal shadow-sm transition-colors hover:border-muted-foreground/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" value={execution} onChange={event=>{setExecution(event.target.value);setSelected("");setScope({})}}>
              {executions.map(id=><option key={id} value={id}>{time(runs.find(run=>run.execution===id)!.started)} &middot; {id}</option>)}
            </select><ChevronDown className="pointer-events-none absolute right-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" aria-hidden="true"/>
          </span>
        </label>
        {visible.length>0&&<div className="flex items-center gap-5 text-xs text-muted-foreground"><span>{visible.length} agent {visible.length===1?"run":"runs"}</span><span className="tabular-nums">{((end-start)/1000).toFixed(1)}s</span></div>}
      </header>
      <div className="p-5">
        {error&&<p role="alert" className="mb-4">{error}</p>}
        {!error&&!runs.length&&<p>No captured agent runs yet.</p>}
        {targetNode&&runs.length>0&&!visible.some(run=>run.node===targetNode)&&<p className="mb-4 text-sm text-muted-foreground">No captured activity for the selected node in this graph execution.</p>}
        {visible.length>0&&<ActivityTimeline runs={visible} details={details} selected={selected} scope={scope} start={start} end={end} label={label} onSelect={selectScope}/>}
    {detail&&<article key={detail.run.id} className="mt-6 flex flex-col gap-12" aria-label="Selected agent run">
      <div className="space-y-4">
      <nav aria-label="Activity selection" className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
        <span>{time(detail.run.started)}</span><span aria-hidden="true">/</span>
        <button className="hover:text-foreground focus-visible:outline focus-visible:outline-2" aria-current={!scope.thread?"page":undefined} onClick={()=>setScope({})}>All activity</button>
        {breadcrumbs.map(thread=><span key={thread.id} className="contents"><span aria-hidden="true">/</span><button className="max-w-full break-words hover:text-foreground focus-visible:outline focus-visible:outline-2" aria-current={scope.thread===thread.id&&!scope.turn?"page":undefined} onClick={()=>setScope({thread:thread.id})}>{thread.title}</button></span>)}
        {currentTurn&&<span aria-current="page">/ Turn {currentConversation!.turns.indexOf(currentTurn)+1}</span>}
      </nav>
      <section className="space-y-3" aria-label="Invocation metadata">
        <div className="flex min-w-0 flex-wrap items-start justify-between gap-2"><h3 className="flex min-w-0 items-center gap-2 break-words text-lg font-semibold"><span aria-hidden="true"><ProviderIcon provider={detail.run.provider}/></span>{currentTurn?`Turn ${currentConversation!.turns.indexOf(currentTurn)+1} · ${currentConversation!.title}`:currentConversation?.id===detail.run.native_session?label(detail.run):currentConversation?.title??label(detail.run)}</h3><div className="flex items-center gap-2 text-xs text-muted-foreground">{statusBadge(selectedLane?.status??"unknown")}<span>{selectedLane&&duration(selectedLane.started,selectedLane.ended)}</span><ActivityInfo label="Usage and cost details" text={`${projection!.usage===null?"Aggregate usage is incomplete. ":""}${projection!.cost_reason}. Cached input is part of input; reasoning is part of output. Charts show captured observations only.${detail.run.provider==="claude"||detail.run.provider==="claude-code"?" Claude activity shows the native events captured for this invocation. Usage is reported only when supplied by Claude. Check the recorded tool activity and cleanup status for this run.":""}`}/></div></div>
        <div className="flex flex-wrap items-start justify-between gap-3 text-xs text-muted-foreground"><p title={selectedLane?.started}>Started {selectedLane&&time(selectedLane.started)} · Provider {detail.run.provider??"codex-cli"} · Model {(scope.thread&&scope.thread!==detail.run.native_session?projection?.cost.model:detail.run.model)??"unconfirmed"} · Captured stream: {detail.run.stream_state}</p>
          <details><summary className="cursor-pointer">Node identity</summary><dl className="mt-2 grid gap-1 break-all"><dt>Node ID</dt><dd>{detail.run.node}</dd><dt>Name source</dt><dd>{detail.run.node_label?"Recorded when this invocation started":"Current canvas name; no name was recorded for this older invocation"}</dd></dl></details>
        </div>

      </section>
      </div>
      {detail.run.reason&&<p className="text-sm" role="status">Capture note: {describeNodeFailure(detail.run.reason,undefined).title} <NodeErrorNotice message={detail.run.reason} context={{nodeId:detail.run.node,nodeLabel:label(detail.run)}}/></p>}
      {detail.truncated&&<p role="alert">This invocation exceeds the detail limit. The view is partial.</p>}
      <section className="min-w-0 space-y-4" aria-label="Usage and cost">
        <UsageCharts key={`usage:${selected}:${scope.thread??""}:${scope.turn??""}`} projection={projection!} scopeLabel={scopeLabel} running={!detail.truncated&&!detail.run.reason&&selectedLane?.status==="running"}/>
      </section>
      <RuntimeRecords key={`records:${selected}:${scope.thread??""}:${scope.turn??""}`} records={projection!.telemetry} coverage={projection!.telemetry_coverage} context={exportContext!}/>
      <Conversation key={`conversation:${selected}:${scope.thread??""}:${scope.turn??""}`} projection={projection!} context={exportContext!}/>
    </article>}
    </div></section>
    <footer className="mt-auto border-t pt-6 pb-2 text-center text-xs text-muted-foreground">
      © {new Date().getFullYear()} Laomedo contributors. MIT License.
    </footer>
    </div></div></div>
  </section>;
}
