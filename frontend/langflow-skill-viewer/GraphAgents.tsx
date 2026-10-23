import { useEffect, useState } from "react";
import Markdown from "react-markdown";
import IconComponent from "@/components/common/genericIconComponent";
import SimplifiedCodeTabComponent from "@/components/core/codeTabsComponent";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useAgentActivityStore } from "@/stores/agentActivityStore";
import useFlowStore from "@/stores/flowStore";
import { api } from "@/controllers/API/api";
import { getBaseUrl } from "@/customization/utils/urls";

type Run = {id:string;node:string;provider?:string;node_label?:string|null;execution:string|null;started:string;ended:string|null;status:string;stream_state:string;reason?:string|null;runner_run_id:string|null;native_session:string|null;model:string|null;event_count:number};
type Lane = {id:string;thread?:string;turn?:string;started:string;ended:string|null;status?:string;item?:Record<string,unknown>;conflicting_receipts?:boolean};
type Cost = {amount:number|null;currency:string;basis:string;catalog_date:string;source:string|null};
type Projection = {turns:Lane[];items:Lane[];threads:{id:string;parent:string|null}[];usage:Record<string,number>|null;usage_points:{at:string;thread:string;usage:Record<string,number>;cost:Cost}[];clock:string;cost:Cost;cost_reason:string;telemetry:Record<string,unknown>[];telemetry_coverage:string;diagnostics?:Record<string,unknown>[]};
type Detail = {run:Run;projection:Projection;truncated:boolean};
const time = (value:string) => new Date(value).toLocaleTimeString(undefined,{hour:"2-digit",minute:"2-digit",second:"2-digit"});
const duration = (start:string,end:string|null) => `${Math.max(0,(Date.parse(end??new Date().toISOString())-Date.parse(start))/1000).toFixed(1)}s`;
const messageText = (item:Record<string,unknown>|undefined) => {
  if(typeof item?.text==="string")return item.text;
  if(item?.type==="userMessage"&&Array.isArray(item.content))return item.content.map(part=>typeof part?.text==="string"?part.text:"[Non-text content]").join("\n");
  return null;
};

export function HighlightedJson({value}:{value:unknown}) {
  return <SimplifiedCodeTabComponent code={JSON.stringify(value,null,2)??"null"} language="json"/>;
}

// The upstream code font rule is !important; override it locally for transcript code.
export function MessageMarkdown({text}:{text:string}) {
  return <Markdown skipHtml disallowedElements={["img"]} className="prose prose-sm max-w-none break-words dark:prose-invert prose-code:before:content-none prose-code:after:content-none prose-code:!font-mono prose-code:font-normal [&_pre]:overflow-x-auto [&_pre]:whitespace-pre-wrap [&_code]:break-words" components={{code:({node,...props})=><code {...props} style={{fontFamily:"ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",fontWeight:400}}/>,a:({node,...props})=><a {...props} target="_blank" rel="noopener noreferrer"/>}}>{text}</Markdown>;
}

function SectionHeading({children,id}:{children:React.ReactNode;id?:string}) {
  return <div className="flex min-w-0 items-center gap-5"><h2 id={id} className="shrink-0 text-xs font-semibold uppercase tracking-wide text-muted-foreground">{children}</h2><div className="h-px min-w-4 flex-1 bg-border"/></div>;
}

function JsonDisclosure({label,value,className}:{label:string;value:unknown;className?:string}) {
  const [open,setOpen]=useState(false);
  return <details className={className} onToggle={event=>setOpen(event.currentTarget.open)}><summary className="cursor-pointer text-xs text-muted-foreground">{label}</summary>{open&&<div className="mt-2 min-w-0"><HighlightedJson value={value}/></div>}</details>;
}

function MessageSource({value}:{value:unknown}) {
  const [open,setOpen]=useState(false);
  return <Popover open={open} onOpenChange={setOpen}>
    <PopoverTrigger asChild><Button variant="ghost" size="icon" className="h-5 w-5 shrink-0 text-muted-foreground" title="View message source" aria-label="View message source"><IconComponent name="Code" className="h-3.5 w-3.5"/></Button></PopoverTrigger>
    <PopoverContent align="end" collisionPadding={12} aria-label="Message source" className="max-h-[70vh] w-[min(520px,calc(100vw-2rem))] overflow-auto p-3" onKeyDown={event=>event.stopPropagation()}>
      <div className="flex items-center justify-between gap-3"><h3 className="text-sm font-medium">Message source</h3><Button variant="ghost" size="icon" className="h-6 w-6" aria-label="Close message source" onClick={()=>setOpen(false)}><IconComponent name="X" className="h-3.5 w-3.5"/></Button></div>
      {open&&<HighlightedJson value={value}/>}
    </PopoverContent>
  </Popover>;
}

export function commandTitle(value:Record<string,unknown>) {
  if(Array.isArray(value.commandActions)) {
    const read=value.commandActions.find(action=>action&&typeof action==="object"&&action.type==="read"&&typeof action.name==="string");
    if(read)return `Read ${read.name}`;
  }
  return "Shell command";
}

export function activityTitle(value:Record<string,unknown>) {
  if(value.type==="commandExecution")return commandTitle(value);
  if(value.type==="subAgentActivity") {
    const action=value.kind==="started"?"Subagent started":value.kind==="completed"?"Subagent completed":"Subagent activity";
    const target=typeof value.agentPath==="string"?value.agentPath:typeof value.agentThreadId==="string"?value.agentThreadId.slice(-8):"";
    return target?`${action} · ${target}`:action;
  }
  if(value.type==="collabAgentToolCall"||value.type==="collabAgentSpawnToolCall")return `Subagent tool${typeof value.tool==="string"?`: ${value.tool}`:""}${typeof value.status==="string"?` · ${value.status}`:""}`;
  return String(value.type??"Tool activity");
}

function ActivityItem({lane,rootThread,provider}:{lane:Lane;rootThread:string|null;provider?:string}) {
  const value=lane.item??{},message=messageText(value),user=value.type==="userMessage";
  const child=Boolean(rootThread&&lane.thread&&lane.thread!==rootThread);
  const providerName=provider==="claude"||provider==="claude-code"?"Claude":provider==="opencode"||provider==="opencode-cli"?"OpenCode":!provider||provider==="codex"||provider==="codex-cli"?"Codex":"Agent";
  const speaker=child?`Subagent ${lane.thread!.slice(-8)}`:providerName;
  const timing=<span title={`${lane.started} → ${lane.ended??"running"}`} className="tabular-nums">{time(lane.started)}{!user&&` · ${duration(lane.started,lane.ended)}`}</span>;
  if(message!==null)return <div className={`flex min-w-0 flex-col gap-2 ${user?"items-end":"items-start"}`} data-message-role={user?"user":"agent"}>
    <div className="flex w-full min-w-0 items-center gap-2 text-xs text-muted-foreground"><div className={`flex flex-wrap items-center gap-2 ${user?"ml-auto":"flex-1"}`}><span title={lane.thread}>{user?"You":speaker}</span>{timing}</div><MessageSource value={value}/></div>
    {lane.conflicting_receipts&&<p role="status" className="text-xs">Conflicting native receipts retained.</p>}
    <div className={user?"max-w-[85%] rounded-md border bg-muted/50 px-4 py-3 text-sm":"w-full min-w-0 text-sm"}><MessageMarkdown text={message}/></div>
  </div>;
  const command=value.type==="commandExecution";
  const output=typeof value.aggregatedOutput==="string"?value.aggregatedOutput:null;
  return <div className="min-w-0 border-y bg-muted/40 px-3 py-2" data-testid="agent-tool-row">
    <div className="flex min-w-0 flex-wrap items-start gap-x-4 gap-y-1 text-xs">
      <span className="flex min-w-0 items-center gap-2 text-muted-foreground"><IconComponent name="Terminal" className="h-3.5 w-3.5 shrink-0"/><span className="break-words">{activityTitle(value)}</span></span>
      {command&&<code className="min-w-0 flex-1 whitespace-pre-wrap break-words text-foreground !font-mono">{String(value.command??"Command not retained")}</code>}
      {command&&<span className="ml-auto shrink-0 tabular-nums">Exit: {String(value.exitCode??"Unknown")}</span>}
    </div>
    {lane.conflicting_receipts&&<p role="status" className="mt-1 text-xs">Conflicting native receipts retained.</p>}
    <div className="mt-2 flex min-w-0 flex-wrap items-start gap-x-5 gap-y-2 text-xs text-muted-foreground">
      <span>{child&&<span title={lane.thread}>{speaker} · </span>}{timing}{typeof value.cwd==="string"&&` · ${value.cwd}`}</span>
      {command&&<details className="min-w-0 basis-full sm:basis-auto open:!basis-full"><summary className="cursor-pointer">Output{output!==null?` (${output.length?output.replace(/\r?\n$/, "").split(/\r?\n/).length:0} lines)`:""}</summary><pre className="mt-2 max-w-full overflow-auto whitespace-pre-wrap break-words text-xs text-foreground">{output??"Output not retained"}</pre></details>}
      <JsonDisclosure className="min-w-0 basis-full sm:basis-auto open:!basis-full" label="Native tool metadata" value={value}/>
    </div>
  </div>;
}

export default function GraphAgents({flowId}:{flowId?:string}) {
  const nodes=useFlowStore(state=>state.nodes);
  const target=useAgentActivityStore(state=>state.target);
  const targetNode=target?.flowId===flowId?target.nodeId:undefined;
  useEffect(()=>()=>useAgentActivityStore.getState().clearTarget(),[]);
  useEffect(()=>{setExecution("");setSelected("")},[targetNode]);
  const label=(run:Run)=>run.node_label?.trim()||nodes.find(node=>node.id===run.node)?.data.node?.display_name||run.node;
  const statusBadge=(status:string)=><Badge size="tag" variant={status==="completed"?"successStatic":status==="running"?"secondaryStatic":"errorStatic"}>{status}</Badge>;
  const [runs,setRuns]=useState<Run[]>([]),[execution,setExecution]=useState("");
  const [details,setDetails]=useState<Record<string,Detail>>({}),[selected,setSelected]=useState("");
  const [error,setError]=useState(""),[refresh,setRefresh]=useState(0);
  const base=`${getBaseUrl()}laomedo/agent-executions/${encodeURIComponent(flowId??"")}`;
  useEffect(()=>{setRuns([]);setExecution("");setDetails({});setSelected("")},[flowId]);
  useEffect(()=>{setDetails({})},[execution]);
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
    if(!targetNode)return;
    setSelected(current=>visible.some(run=>run.id===current)?current:[...visible].filter(run=>run.node===targetNode).sort((a,b)=>b.started.localeCompare(a.started))[0]?.id??"");
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
  const span=Math.max(1000,end-start);
  const detail=details[selected];
  const executions=[...new Set(runs.map(run=>run.execution).filter((value):value is string=>Boolean(value)))];
  const bar=(lane:Lane,label:string,onClick:()=>void,invocation:string,child=false)=><div key={lane.id} className={`grid min-w-[700px] grid-cols-[280px_1fr] items-center border-b border-border last:border-b-0 ${selected===invocation?"bg-muted/50":""}`}>
    <button className={`flex min-w-0 items-center gap-2 px-3 py-2 text-left text-sm hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring ${child?"pl-8":"font-medium"}`} onClick={onClick} title={label} aria-label={label} aria-pressed={selected===invocation}>
      <IconComponent name={child?"CornerDownRight":"Bot"} className="h-4 w-4 shrink-0 text-muted-foreground"/>
      <span className="min-w-0 flex-1 truncate">{label.replace(/ · [^·]+$/,"")}</span>
      {statusBadge(lane.status??"unknown")}
    </button>
    <div className="relative mx-3 h-8"><button aria-label={`${label}, ${duration(lane.started,lane.ended)}`} title={`${lane.started} → ${lane.ended??"running"}`} onClick={onClick}
      className={`absolute top-1.5 h-5 min-w-2 rounded-sm border text-[10px] tabular-nums focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${lane.status==="completed"?"border-accent-emerald-foreground/30 bg-accent-emerald text-accent-emerald-foreground":lane.status==="running"?"border-ring bg-secondary text-secondary-foreground":"border-error-foreground/30 bg-error-background text-error-foreground"}`}
      style={{left:`${Math.max(0,(Date.parse(lane.started)-start)/span*100)}%`,width:`${Math.max(.5,Math.min(100,(Date.parse(lane.ended??new Date().toISOString())-Date.parse(lane.started))/span*100))}%`}}>
      {duration(lane.started,lane.ended)}</button></div></div>;
  return <section className="flex h-full min-w-0 flex-1 flex-col overflow-hidden bg-background text-foreground" aria-label="Graph agent activity">
    <header className="flex min-h-12 shrink-0 items-center justify-between gap-3 border-b px-4 py-3"><h1 className="text-sm font-semibold">Agents</h1>
      <Button variant="ghost" size="icon" aria-label="Refresh" onClick={()=>setRefresh(value=>value+1)}><IconComponent name="RefreshCcw" className="h-4 w-4"/></Button></header>
    <div className="min-w-0 flex-1 overflow-y-auto overflow-x-hidden">
    <div className="space-y-3 border-b px-4 py-3"><p className="text-sm text-muted-foreground">Recorded executions of the current graph.</p>
    <label className="flex flex-wrap items-center gap-3 text-sm">Graph execution <select className="max-w-full rounded-md border bg-background px-3 py-1.5 text-sm" value={execution} onChange={event=>{setExecution(event.target.value);setSelected("")}}>
      {executions.map(id=><option key={id} value={id}>{time(runs.find(run=>run.execution===id)!.started)} · {id}</option>)}</select></label></div>
    <div className="min-w-0 p-4">
    {error&&<p role="alert" className="mb-4">{error}</p>}
    {!error&&!runs.length&&<p>No captured agent runs yet.</p>}
    {targetNode&&runs.length>0&&!visible.some(run=>run.node===targetNode)&&<p className="mb-4 text-sm text-muted-foreground">No captured activity for the selected node in this graph execution.</p>}
    {visible.length>0&&<><div className="mb-4"><SectionHeading>Graph run timeline</SectionHeading></div><div className="overflow-x-auto rounded-md border border-border"><div className="flex min-w-[700px] justify-between border-b bg-muted/40 py-2 pl-[292px] pr-3 text-xs tabular-nums text-muted-foreground"><span>{time(new Date(start).toISOString())}</span><span>{((end-start)/1000).toFixed(1)} seconds</span><span>{time(new Date(end).toISOString())}</span></div>
      {visible.map(run=><div key={run.id}>{bar({...run,id:run.id},`${label(run)} · ${run.status}`,()=>setSelected(run.id),run.id)}
        {details[run.id]?.projection.turns.map(turn=>bar(turn,`${turn.thread===run.native_session?"Turn":"Subagent turn"} ${turn.id.slice(-8)} · ${turn.status}`,()=>setSelected(run.id),run.id,true))}</div>)}</div>
      <p className="my-2 text-xs text-muted-foreground">Bars use runner receipt times. Viewing activity never starts an agent. Select an invocation to inspect it.</p></>}
    {detail&&<article key={detail.run.id} className="mt-8 space-y-6" aria-label="Selected agent run">
      <SectionHeading>Selected agent run</SectionHeading>
      <section className="space-y-3 border bg-muted/30 px-4 py-3" aria-label="Invocation metadata">
        <div className="flex min-w-0 flex-wrap items-start justify-between gap-2"><h3 className="min-w-0 break-words text-lg font-semibold">{label(detail.run)}</h3><div className="flex items-center gap-2 text-xs text-muted-foreground">{statusBadge(detail.run.status)}<span>{duration(detail.run.started,detail.run.ended)}</span></div></div>
        <div className="flex flex-wrap items-start justify-between gap-3 text-xs text-muted-foreground"><p title={detail.run.started}>Started {time(detail.run.started)} · Model {detail.run.model??"unconfirmed"} · Captured stream: {detail.run.stream_state}</p>
          <details><summary className="cursor-pointer">Node identity</summary><dl className="mt-2 grid gap-1 break-all"><dt>Node ID</dt><dd>{detail.run.node}</dd><dt>Name source</dt><dd>{detail.run.node_label?"Recorded when this invocation started":"Current canvas name; no name was recorded for this older invocation"}</dd></dl></details>
        </div>
        <dl className="flex flex-wrap gap-x-5 gap-y-2 text-xs text-muted-foreground">{[["inputTokens","Input"],["cachedInputTokens","Cached input"],["outputTokens","Output"],["reasoningOutputTokens","Reasoning"]].map(([key,name])=><div key={key} className="flex gap-1.5"><dt>{name}</dt><dd className="tabular-nums text-foreground">{detail.projection.usage?.[key]?.toLocaleString()??"Unknown"}</dd></div>)}<div className="flex gap-1.5"><dt>API-equivalent estimate</dt><dd className="tabular-nums text-foreground">{detail.projection.cost.amount===null?"Unknown":`$${detail.projection.cost.amount.toFixed(6)}`}</dd></div></dl>
      </section>
      {detail.run.reason&&<p className="text-sm" role="status">Capture note: {detail.run.reason.replaceAll("_"," ")}</p>}
      {detail.truncated&&<p role="alert">This invocation exceeds the detail limit. The view is partial.</p>}
      <section className="min-w-0 space-y-4 rounded-md border p-4" aria-label="Usage and diagnostics">
        <h3 className="text-sm font-semibold">Usage and diagnostics</h3>
        {(detail.run.provider==="claude-code"||detail.run.provider==="claude")&&<p className="text-xs text-muted-foreground">Claude Code proposal mode: native tools and subagents are disabled. Prompts are host-submitted; answers and usage come from terminal receipts. Feed completion does not establish complete execution evidence.</p>}
        {detail.projection.diagnostics?.map((value,index)=><JsonDisclosure key={index} label={`Claude terminal receipt ${index+1}`} value={value}/>)}
        <details open><summary className="cursor-pointer text-xs text-muted-foreground">Tokens and API-equivalent cost over time</summary><div className="mt-3 overflow-x-auto"><table className="w-full min-w-[600px] text-left text-xs tabular-nums"><thead className="text-muted-foreground"><tr><th className="py-2 font-normal">Observed</th><th className="font-normal">Thread</th>{["Input","Cached input","Output","Estimate (USD)"].map(name=><th key={name} className="text-right font-normal">{name}</th>)}</tr></thead><tbody>{detail.projection.usage_points.map((point,index)=><tr key={index}><td className="py-1" title={point.at}>{time(point.at)}</td><td>{point.thread.slice(0,8)}</td>{["inputTokens","cachedInputTokens","outputTokens"].map(key=><td className="text-right" key={key}>{point.usage[key]?.toLocaleString()??"Unknown"}</td>)}<td className="text-right">{point.cost?.amount==null?"Unknown":`$${point.cost.amount.toFixed(6)}`}</td></tr>)}</tbody></table></div></details>
        <p className="text-xs text-muted-foreground">{detail.projection.cost_reason} Cached input is part of input; reasoning is part of output.</p>
        <JsonDisclosure label="Thread and subagent links" value={detail.projection.threads}/>
        <details><summary className="cursor-pointer text-xs text-muted-foreground">OpenTelemetry · {detail.projection.telemetry.length} records</summary><p className="my-2 text-sm">{detail.projection.telemetry_coverage}. Runtime spans are not counted as agent invocations or token charges.</p>{detail.projection.telemetry.slice(0,50).map((record,index)=><JsonDisclosure key={index} label={`Runtime record ${index+1}`} value={record}/>)}{detail.projection.telemetry.length>50&&<p>Showing the first 50 runtime records.</p>}</details>
      </section>
      <section aria-labelledby="agent-conversation-heading" className="min-w-0 space-y-4">
        <SectionHeading id="agent-conversation-heading">Conversation</SectionHeading>
        <div role="region" aria-label="Conversation messages and tools" tabIndex={0} className="max-h-[min(360px,60vh)] [scrollbar-width:thin] [scrollbar-gutter:stable] min-w-0 space-y-5 overflow-y-auto px-3 pb-3 pr-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
          {detail.projection.items.length===0&&<p className="text-sm text-muted-foreground">No messages or tool calls captured.</p>}
          {detail.projection.items.map(item=><ActivityItem key={`${item.thread}:${item.id}`} lane={item} rootThread={detail.run.native_session} provider={detail.run.provider}/>)}
        </div>
      </section>
    </article>}
    </div></div>
  </section>;
}
