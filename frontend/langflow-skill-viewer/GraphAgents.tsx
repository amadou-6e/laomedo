import { useEffect, useId, useMemo, useState } from "react";
import Fuse from "fuse.js";
import NodeErrorNotice from "@/components/laomedoErrors/NodeErrorNotice";
import { describeNodeFailure } from "@/components/laomedoErrors/nodeErrors";
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

type Run = {provider?:string;id:string;node:string;node_label?:string|null;execution:string|null;started:string;ended:string|null;status:string;stream_state:string;reason?:string|null;runner_run_id:string|null;native_session:string|null;model:string|null;event_count:number};
type Lane = {id:string;thread?:string;turn?:string;started:string;ended:string|null;status?:string;usage?:Record<string,number>|null;cost?:Cost;item?:Record<string,unknown>;conflicting_receipts?:boolean};
type Cost = {amount:number|null;currency:string;basis:string;catalog_date:string;source:string|null;model?:string|null;per_thread?:Record<string,Cost>;reason?:string|null};
type Projection = {turns:Lane[];items:Lane[];threads:{id:string;parent:string|null;title?:string}[];usage_by_thread?:Record<string,Record<string,number>|null>;usage:Record<string,number>|null;usage_points:{at:string;thread:string;turn?:string;turn_usage?:Record<string,number>|null;turn_cost?:Cost;usage:Record<string,number>;cost:Cost}[];clock:string;cost:Cost;cost_reason:string;telemetry:Record<string,unknown>[];telemetry_coverage:string};
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

function SectionHeading({children,id,actions}:{children:React.ReactNode;id?:string;actions?:React.ReactNode}) {
  return <div className="flex min-w-0 items-center gap-5"><h2 id={id} className="shrink-0 text-xs font-semibold uppercase tracking-wide text-muted-foreground">{children}</h2><div className="h-px min-w-4 flex-1 bg-border"/>{actions&&<div className="flex shrink-0 items-center gap-2">{actions}</div>}</div>;
}

function ActivityInfo({label,text}:{label:string;text:string}) {
  return <Popover><PopoverTrigger asChild><Button variant="ghost" size="icon" className="h-6 w-6 text-muted-foreground" aria-label={label}><IconComponent name="Info" className="h-3.5 w-3.5"/></Button></PopoverTrigger><PopoverContent className="max-w-[calc(100vw-2rem)] text-xs" align="end">{text}</PopoverContent></Popover>;
}

type ExportContext = {graph_id?:string;run_id:string;execution_id:string|null;node_id:string;provider?:string;model:string|null;native_session:string|null;scope:ActivityScope;capture_state:string;capture_reason?:string|null;truncated:boolean};

function safeExportContext(context:ExportContext):ExportContext {
  return {...context,capture_reason:context.capture_reason?describeNodeFailure(context.capture_reason,undefined).diagnostics.code:null};
}

export function telemetryDocument(records:Record<string,unknown>[],coverage:string,context:ExportContext|undefined,query:string) {
  return JSON.stringify({schema_version:1,kind:"opentelemetry_records",context:context?safeExportContext(context):undefined,search:query,coverage,records},null,2);
}

export function conversationMatches(items:Lane[],query:string) {
  if(!query.trim())return items;
  const entries=items.map((lane,index)=>({index,text:JSON.stringify(lane)}));
  const matches=new Set(new Fuse(entries,{keys:["text"],threshold:.35,ignoreLocation:true,minMatchCharLength:2}).search(query.trim()).map(result=>result.item.index));
  return items.filter((_,index)=>matches.has(index));
}

export function conversationDocument(items:Lane[],context:ExportContext,query:string,format:"md"|"json") {
  context=safeExportContext(context);
  if(format==="json")return JSON.stringify({schema_version:1,kind:"conversation",context,search:query,items},null,2);
  const fence=(text:string)=>{let length=3;for(const match of text.matchAll(/`+/g))length=Math.max(length,match[0].length+1);const marker="`".repeat(length);return `${marker}json\n${text}\n${marker}`};
  return [`# Agent conversation`,`Graph: ${context.graph_id??"Unknown"}\nRun: ${context.run_id}\nExecution: ${context.execution_id??"Unknown"}\nProvider: ${context.provider??"Unknown"}\nModel: ${context.model??"Unknown"}\nScope: ${JSON.stringify(context.scope)}\nCapture: ${context.capture_state}${context.truncated?" (partial)":""}\nCapture warning: ${context.capture_reason??"None"}\nSearch: ${JSON.stringify(query)}`,
    ...items.map(lane=>{const value=lane.item??{},text=messageText(value),speaker=value.type==="userMessage"?"User":lane.thread&&lane.thread!==context.native_session?"Subagent":"Agent";return `## ${text!==null?speaker:activityTitle(value)} · ${lane.started}\n\nThread: ${lane.thread??"Unknown"}${lane.turn?` · Turn: ${lane.turn}`:""}\n\n${text??fence(JSON.stringify(value,null,2))}`})].join("\n\n")+"\n";
}

function downloadActivity(content:string,name:string,type:string) {
  const url=URL.createObjectURL(new Blob([content],{type}));
  const link=document.createElement("a");link.href=url;link.download=name;
  document.body.appendChild(link);
  try{link.click()}finally{link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000)}
}

function Conversation({projection,context}:{projection:Projection;context:ExportContext}) {
  const [query,setQuery]=useState("");
  const [exportOpen,setExportOpen]=useState(false);
  const items=useMemo(()=>conversationMatches(projection.items,query),[projection.items,query]);
  const exportFile=(format:"md"|"json")=>{downloadActivity(conversationDocument(items,context,query,format),`conversation-${context.run_id}.${format}`,format==="md"?"text/markdown;charset=utf-8":"application/json");setExportOpen(false)};
  return <section aria-labelledby="agent-conversation-heading" className="min-w-0 space-y-4">
    <SectionHeading id="agent-conversation-heading" actions={<Popover open={exportOpen} onOpenChange={setExportOpen}><PopoverTrigger asChild><Button variant="ghost" size="sm" className="h-7 gap-1.5 px-2 text-xs" aria-label="Export conversation" disabled={!items.length} title={`Export ${items.length} matching conversation records`}><IconComponent name="Download" className="h-3.5 w-3.5"/>Export</Button></PopoverTrigger><PopoverContent align="end" className="w-44 p-1"><Button variant="ghost" className="w-full justify-start" onClick={()=>exportFile("md")}>Markdown (.md)</Button><Button ignoreTitleCase variant="ghost" className="w-full justify-start" onClick={()=>exportFile("json")}>JSON (.json)</Button></PopoverContent></Popover>}>Conversation</SectionHeading>
    <div className="flex min-w-0 items-center gap-3"><div className="relative min-w-0 flex-1"><IconComponent name="Search" className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted-foreground"/><input value={query} onChange={event=>setQuery(event.target.value)} aria-label="Search conversation" placeholder="Search messages and tools..." className="h-9 w-full rounded-md border bg-background pl-9 pr-16 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"/>{query&&<button type="button" onClick={()=>setQuery("")} className="absolute right-3 top-2 text-xs text-muted-foreground underline">Clear</button>}</div><span role="status" className="shrink-0 text-xs text-muted-foreground">{items.length} of {projection.items.length}</span></div>
    <div role="region" aria-label="Conversation messages and tools" tabIndex={0} className="max-h-[min(360px,60vh)] [scrollbar-width:thin] [scrollbar-gutter:stable] min-w-0 space-y-5 overflow-y-auto px-3 pb-3 pr-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
      {!items.length&&<p className="text-sm text-muted-foreground">{projection.items.length?"No matching messages or tools.":"No messages or tool calls captured."}</p>}
      {items.map(item=><ActivityItem key={`${item.thread}:${item.id}`} lane={item} rootThread={context.native_session} provider={context.provider}/>)}
    </div>
  </section>;
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
  if(value.type==="mcpToolCall")return [value.server,value.tool].filter(part=>typeof part==="string"&&part).join(" · ")||"MCP tool";
  if(value.type==="dynamicToolCall")return typeof value.tool==="string"?value.tool:"Tool call";
  if(value.type==="toolCall"&&typeof value.toolName==="string")return value.toolName;
  return String(value.type??"Tool activity");
}

function ActivityItem({lane,rootThread,provider}:{lane:Lane;rootThread:string|null;provider?:string}) {
  const value=lane.item??{},message=messageText(value),user=value.type==="userMessage";
  const child=Boolean(rootThread&&lane.thread&&lane.thread!==rootThread);
  const speaker=child?`Subagent ${lane.thread!.slice(-8)}`:provider==="opencode"?"OpenCode":"Codex";
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

type UsagePoint = Projection["usage_points"][number];
type ChartPoint = {at:string;usage:Record<string,number>|null;cost:number|null};
const tokenSeries = [
  {key:"inputTokens",label:"Input",color:"#2563eb"},
  {key:"cachedInputTokens",label:"Cached input",color:"#0d9488"},
  {key:"outputTokens",label:"Output",color:"#d97706"},
  {key:"reasoningOutputTokens",label:"Reasoning",color:"#9333ea"},
];

// Each point is cumulative within its thread. Carry forward its latest value,
// then sum threads, rather than adding repeated cumulative observations.
export function aggregateUsagePoints(points:UsagePoint[]):ChartPoint[] {
  const latest=new Map<string,UsagePoint>();
  const ordered=points.filter(point=>Number.isFinite(Date.parse(point.at))).slice().sort((a,b)=>Date.parse(a.at)-Date.parse(b.at));
  const result:ChartPoint[]=[];
  for(let index=0;index<ordered.length;) {
    const at=ordered[index].at,stamp=Date.parse(at);
    do {latest.set(ordered[index].thread,ordered[index]);index++} while(index<ordered.length&&Date.parse(ordered[index].at)===stamp);
    const values=[...latest.values()];
    const usage:Record<string,number>={};
    for(const series of tokenSeries) {
      if(values.every(point=>Number.isFinite(point.usage?.[series.key])))usage[series.key]=values.reduce((total,point)=>total+point.usage[series.key],0);
    }
    const cost=values.every(point=>point.cost?.amount!=null&&Number.isFinite(point.cost.amount))?values.reduce((total,point)=>total+point.cost.amount!,0):null;
    result.push({at,usage:Object.keys(usage).length?usage:null,cost});
  }
  return result;
}

export function turnPosition(turn:Lane,start:number,end:number) {
  const from=Math.max(start,Date.parse(turn.started));
  const to=Math.min(end,Date.parse(turn.ended??new Date().toISOString()));
  if(!Number.isFinite(from)||!Number.isFinite(to)||to<=from||end<=start)return null;
  return {left:(from-start)/(end-start)*100,width:(to-from)/(end-start)*100};
}

export type ActivityScope = {thread?:string;turn?:string};

export function conversationRows(projection:Projection,rootThread:string|null) {
  const entries=new Map(projection.threads.map(thread=>[thread.id,thread]));
  if(rootThread&&!entries.has(rootThread))entries.set(rootThread,{id:rootThread,parent:null});
  for(const lane of [...projection.turns,...projection.items])if(lane.thread&&!entries.has(lane.thread))entries.set(lane.thread,{id:lane.thread,parent:null});
  const rows:{id:string;parent:string|null;title:string;depth:number;turns:Lane[];lane:Lane|null}[]=[];
  const seen=new Set<string>();
  const visit=(id:string,depth:number)=>{
    if(seen.has(id))return;seen.add(id);
    const entry=entries.get(id)!;
    const turns=projection.turns.filter(turn=>turn.thread===id).slice().sort((a,b)=>Date.parse(a.started)-Date.parse(b.started));
    const title=id===rootThread?"Main conversation":entry.title?.trim()||`${entry.parent?"Subagent":"Conversation"} ${rows.length+1}`;
    const running=turns.some(turn=>!turn.ended);
    const status=running?"running":turns.some(turn=>turn.status!=="completed")?"incomplete":turns.length?"completed":"unknown";
    const lane=turns.length?{id,thread:id,started:turns[0].started,ended:running?null:turns.reduce((last,turn)=>Date.parse(turn.ended!)>Date.parse(last)?turn.ended!:last,turns[0].ended!),status}:null;
    rows.push({id,parent:entry.parent,title,depth,turns,lane});
    for(const child of entries.values())if(child.parent===id)visit(child.id,Math.min(depth+1,8));
  };
  for(const entry of entries.values())if(!entry.parent||!entries.has(entry.parent))visit(entry.id,0);
  for(const entry of entries.values())visit(entry.id,0); // Defensive: retain cyclic/orphan provider metadata without recursing forever.
  return rows;
}

export function scopedProjection(projection:Projection,scope:ActivityScope):Projection {
  if(!scope.thread)return projection;
  const items=projection.items.filter(item=>item.thread===scope.thread&&(!scope.turn||item.turn===scope.turn));
  const turns=projection.turns.filter(turn=>turn.thread===scope.thread&&(!scope.turn||turn.id===scope.turn));
  const points=projection.usage_points.filter(point=>point.thread===scope.thread&&(!scope.turn||point.turn===scope.turn));
  const usagePoints=scope.turn?points.filter(point=>point.turn_usage!=null).map(point=>({...point,usage:point.turn_usage!,cost:point.turn_cost??{...projection.cost,amount:null}})):points;
  const usage=scope.turn?turns[0]?.usage??null:projection.usage_by_thread?.[scope.thread]??null;
  const cost=scope.turn?turns[0]?.cost??{...projection.cost,amount:null}:projection.cost.per_thread?.[scope.thread]??{...projection.cost,amount:null};
  const ids=new Set(items.map(item=>item.id));
  const telemetry=projection.telemetry.filter(record=>{
    if(record.scope_conflict)return false;
    const attrs=(record.attributes??{}) as Record<string,unknown>;
    return attrs["conversation.id"]===scope.thread&&(!scope.turn||attrs["turn.id"]===scope.turn||typeof attrs["call.id"]==="string"&&ids.has(attrs["call.id"]));
  });
  return {...projection,items,turns,usage,cost,usage_points:usagePoints,telemetry,cost_reason:cost.reason||cost.basis||"Scoped cost is unavailable",telemetry_coverage:`${projection.telemetry_coverage}. Only explicitly linked records are included; All activity retains unscoped records.`};
}

export function UsageCharts({projection,scopeLabel="Run",running=false}:{projection:Projection;scopeLabel?:string;running?:boolean}) {
  const awaitingUsage=running&&projection.usage===null&&projection.cost.amount===null&&projection.usage_points.length===0;
  const points=useMemo(()=>aggregateUsagePoints(projection.usage_points),[projection.usage_points]);
  const [selected,setSelected]=useState<number|null>(null);
  const [inspected,setInspected]=useState<string|null>(null);
  const instructionId=useId();
  useEffect(()=>{setSelected(null);setInspected(null)},[projection]);
  const current=points[Math.min(selected??points.length-1,points.length-1)];
  const metrics=[...tokenSeries,{key:"cost",label:"API-equivalent estimate",color:"#0d9488"}];
  const amount=(value:number|null|undefined,cost=false)=>value==null?"Unknown":cost?`$${value.toFixed(6)}`:value.toLocaleString("en-US");
  const chart=(cost:boolean)=>{
    const series=cost?[metrics[4]]:[tokenSeries[0],tokenSeries[1],tokenSeries[3],tokenSeries[2]];
    const value=(point:ChartPoint,key:string)=>key==="cost"?point.cost:point.usage?.[key];
    const chartId=cost?"cost":"tokens";
    if(cost&&points.every(point=>point.cost===null))return <div role="img" aria-label="Estimated cost unavailable" className="min-w-0 rounded-md border p-3"><p className="text-xs font-medium">API-equivalent cost (USD)</p><p className="py-12 text-sm text-muted-foreground">Unknown — no priced observations captured for this selection.</p></div>;
    const max=Math.max(cost?0.000001:1,...points.flatMap(point=>series.map(line=>value(point,line.key)??0)));
    const first=Date.parse(points[0].at),last=Date.parse(points[points.length-1].at);
    const x=(point:ChartPoint)=>last===first?330:58+(Date.parse(point.at)-first)/(last-first)*544;
    const y=(number:number)=>164-number/max*136;
    return <figure tabIndex={0} aria-describedby={`${instructionId}-${chartId}`} onFocus={()=>{setInspected(chartId);setSelected(index=>index??points.length-1)}} onBlur={()=>setInspected(null)} onMouseEnter={()=>setInspected(chartId)} onMouseLeave={event=>{if(document.activeElement!==event.currentTarget)setInspected(null)}} onKeyDown={event=>{if(!["ArrowLeft","ArrowRight","Home","End"].includes(event.key))return;event.preventDefault();setSelected(index=>event.key==="Home"?0:event.key==="End"?points.length-1:Math.max(0,Math.min(points.length-1,(index??points.length-1)+(event.key==="ArrowLeft"?-1:1))))}} className="relative min-w-0 rounded-md border p-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" aria-label={cost?"Cumulative estimated cost chart":"Cumulative token usage chart"}>
      <p id={`${instructionId}-${chartId}`} className="sr-only">Use Left and Right arrow keys to inspect observations, or Home and End for the first and last.</p>
      <figcaption className="mb-2 text-xs font-medium">{cost?"API-equivalent cost (USD)":"Tokens"}</figcaption>
      {inspected===chartId&&current&&<div role="status" aria-live="polite" className="pointer-events-none absolute right-3 top-8 z-10 max-w-[90%] rounded-md border bg-popover p-2 text-xs text-popover-foreground shadow-md"><p className="mb-1 tabular-nums">{time(current.at)}</p>{series.map(line=><p key={line.key} className="tabular-nums">{line.label}: {amount(value(current,line.key),line.key==="cost")}</p>)}</div>}
      <svg viewBox="0 0 640 205" className="w-full" aria-hidden="true" onMouseMove={event=>{
        const bounds=event.currentTarget.getBoundingClientRect(),position=(event.clientX-bounds.left)/bounds.width*640;
        setInspected(chartId);setSelected(points.reduce((best,point,index)=>Math.abs(x(point)-position)<Math.abs(x(points[best])-position)?index:best,0));
      }}>
        {[0,.5,1].map(ratio=><g key={ratio}><line x1="58" x2="602" y1={y(max*ratio)} y2={y(max*ratio)} stroke="currentColor" opacity=".12"/><text x="50" y={y(max*ratio)+4} textAnchor="end" fontSize="10" fill="currentColor">{cost?(max*ratio).toFixed(6):Math.round(max*ratio).toLocaleString("en-US")}</text></g>)}
        {series.map(line=>{
          let path="",previous=false;
          for(const point of points){const number=value(point,line.key);if(number==null){previous=false;continue}path+=previous?` H ${x(point)} V ${y(number)}`:` M ${x(point)} ${y(number)}`;previous=true}
          return <g key={line.key}><path d={path} fill="none" stroke={line.color} strokeWidth="2"/>{points.map((point,index)=>{const number=value(point,line.key);return number==null?null:<circle key={index} cx={x(point)} cy={y(number)} r={point===current?4:2.5} fill={line.color}/>})}</g>;
        })}
        <text x="58" y="191" fontSize="10" fill="currentColor">{time(points[0].at)}</text>
        {points.length>1&&<text x="602" y="191" textAnchor="end" fontSize="10" fill="currentColor">{time(points[points.length-1].at)}</text>}
      </svg>
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs">{series.map(line=><span key={line.key} className="flex items-center gap-1.5"><span className="h-0.5 w-3" style={{backgroundColor:line.color}}/>{line.label}</span>)}</div>
    </figure>;
  };
  return <section aria-label="Usage overview" className="space-y-4">
    <p className="text-xs font-medium">{scopeLabel} totals</p>
    <div role="group" aria-label={`${scopeLabel} totals`} className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-5">{metrics.map(metric=><div key={metric.key} className="min-w-0 rounded-md border bg-muted/20 px-3 py-3"><p className="text-xs text-muted-foreground">{metric.label}</p><p className="mt-1 break-words text-xl font-semibold tabular-nums">{amount(awaitingUsage?0:metric.key==="cost"?projection.cost.amount:projection.usage?.[metric.key],metric.key==="cost")}</p></div>)}</div>
    {!points.length?<p className="text-sm text-muted-foreground">No timestamped usage captured. Aggregate values are shown above when available.</p>:<>
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground"><h4 className="font-medium text-foreground">Cumulative usage over time</h4><span>{points.length} {points.length===1?"observation":"observations"} · {scopeLabel.toLowerCase()} scope</span></div>
      <div className="grid min-w-0 grid-cols-[repeat(auto-fit,minmax(min(100%,320px),1fr))] gap-3">{chart(false)}{chart(true)}</div>
    </>}
    {projection.usage===null&&!awaitingUsage&&<p role="status" className="text-xs text-muted-foreground">Aggregate usage is incomplete.</p>}
  </section>;
}

export function RuntimeRecords({records,coverage,context}:{records:Record<string,unknown>[];coverage:string;context?:ExportContext}) {
  const [query,setQuery]=useState("");
  const entries=useMemo(()=>records.map((record,index)=>({record,index,text:JSON.stringify(record)})),[records]);
  const search=useMemo(()=>new Fuse(entries,{keys:["text"],threshold:.35,ignoreLocation:true,minMatchCharLength:2}),[entries]);
  const visible=query.trim()?search.search(query.trim()).map(result=>result.item):entries;
  return <section className="min-w-0 space-y-4" aria-label="OpenTelemetry">
    <SectionHeading actions={<><ActivityInfo label="OpenTelemetry capture details" text={`${coverage}. Runtime spans are not counted as agent invocations or token charges.`}/><Button variant="ghost" size="sm" className="h-7 gap-1.5 px-2 text-xs" aria-label="Export OpenTelemetry JSON" disabled={!visible.length} title={`Export ${visible.length} matching OpenTelemetry records`} onClick={()=>downloadActivity(telemetryDocument(visible.map(entry=>entry.record),coverage,context,query),`opentelemetry-${context?.run_id??"records"}.json`,"application/json")}><IconComponent name="Download" className="h-3.5 w-3.5"/>Export</Button></>}>OpenTelemetry</SectionHeading>
    <div className="flex min-w-0 items-center gap-3"><div className="relative min-w-0 flex-1"><IconComponent name="Search" className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted-foreground"/><input value={query} onChange={event=>setQuery(event.target.value)} aria-label="Search OpenTelemetry records" placeholder="Search records by name, thread, tool or metadata..." className="h-9 w-full rounded-md border bg-background pl-9 pr-16 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"/>{query&&<button type="button" onClick={()=>setQuery("")} className="absolute right-3 top-2 text-xs text-muted-foreground underline">Clear</button>}</div><span role="status" className="shrink-0 text-xs text-muted-foreground">{visible.length} of {records.length} records</span></div>
    <div role="region" aria-label="OpenTelemetry records" tabIndex={0} className="max-h-[min(360px,60vh)] overflow-y-auto [scrollbar-width:thin] [scrollbar-gutter:stable] divide-y rounded-md border focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">{visible.map(({record,index})=><div key={index} className="min-w-0 px-3 py-2"><JsonDisclosure label={`${index+1}. ${typeof record.name==="string"?record.name:`Runtime record ${index+1}`}${typeof record.signal==="string"?` / ${record.signal}`:""}`} value={record}/></div>)}{!visible.length&&<p className="p-3 text-sm text-muted-foreground">{records.length?"No matching records. Clear the search to show every record.":"No OpenTelemetry records captured."}</p>}</div>
  </section>;
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
  const detail=details[selected];
  const rowsByRun=useMemo(()=>Object.fromEntries(Object.entries(details).map(([id,value])=>[id,conversationRows(value.projection,value.run.native_session)])),[details]);
  const conversations=rowsByRun[selected]??[];
  const currentConversation=conversations.find(thread=>thread.id===scope.thread);
  const currentTurn=currentConversation?.turns.find(turn=>turn.id===scope.turn);
  const projection=useMemo(()=>detail?scopedProjection(detail.projection,scope):undefined,[detail,scope]);
  const breadcrumbs:typeof conversations=[];
  let ancestor=currentConversation;
  while(ancestor&&!breadcrumbs.some(value=>value.id===ancestor!.id)) {breadcrumbs.unshift(ancestor);ancestor=conversations.find(value=>value.id===ancestor!.parent)}
  const resumedThread=scope.thread??detail?.run.native_session;
  const earlier=detail&&resumedThread?runs.filter(run=>run.id!==detail.run.id&&run.node===detail.run.node&&run.provider===detail.run.provider&&run.native_session===resumedThread&&run.execution&&run.ended&&Date.parse(run.ended)<=Date.parse(detail.run.started)).sort((a,b)=>Date.parse(b.started)-Date.parse(a.started))[0]:undefined;
  const selectScope=(invocation:string,next:ActivityScope={})=>{setSelected(invocation);setScope(next)};
  const scopeLabel=scope.turn?"Turn":scope.thread?"Conversation":"Run";
  const exportContext:ExportContext|undefined=detail?{graph_id:flowId,run_id:detail.run.id,execution_id:detail.run.execution,node_id:detail.run.node,provider:detail.run.provider,model:(scope.thread&&scope.thread!==detail.run.native_session?projection?.cost.model:detail.run.model)??null,native_session:detail.run.native_session,scope,capture_state:detail.run.stream_state,capture_reason:detail.run.reason??null,truncated:detail.truncated}:undefined;
  const selectedLane=currentTurn??currentConversation?.lane??detail?.run;
  const executions=[...new Set(runs.map(run=>run.execution).filter((value):value is string=>Boolean(value)))];
  const agentRow=(run:Run,thread:ReturnType<typeof conversationRows>[number])=>{
    const isRoot=thread.id===run.native_session;
    const name=isRoot?label(run):thread.title;
    const active=selected===run.id&&scope.thread===thread.id;
    const status=thread.lane?.status??"unknown";
    const rowLabel=isRoot?`${name} · ${run.status}`:`${name} · ${thread.turns.length} ${thread.turns.length===1?"turn":"turns"} · ${status}`;
    return <div key={`${run.id}:${thread.id}`} data-testid="agent-timeline-row" data-thread={thread.id} className={`grid min-w-[900px] grid-cols-[360px_1fr] items-center border-b border-border last:border-b-0 ${active?"bg-muted/50":""}`}>
      <button className="flex min-w-0 items-center gap-2 px-3 py-2 text-left text-sm font-medium hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring" style={{paddingLeft:12+Math.min(thread.depth,8)*16}} onClick={()=>selectScope(run.id,{thread:thread.id})} title={rowLabel} aria-label={rowLabel} aria-pressed={active&&!scope.turn}>
        <IconComponent name={isRoot?"Bot":"MessageSquare"} className="h-4 w-4 shrink-0 text-muted-foreground"/>
        <span className="line-clamp-2 min-w-0 flex-1 break-words">{name} · {thread.turns.length} {thread.turns.length===1?"turn":"turns"}</span>
        {statusBadge(status)}
      </button>
      <div className="relative mx-3 h-8" aria-label={`${name} turns`}>
        {thread.turns.map((turn,index)=>{
          const position=turnPosition(turn,start,end);
          if(!position)return null;
          return <button key={turn.id} data-testid="agent-turn-bar" aria-label={`Turn ${index+1} · ${thread.title} · ${turn.status}, ${duration(turn.started,turn.ended)}`} title={`Turn ${index+1} · ${time(turn.started)} → ${turn.ended?time(turn.ended):"running"}`} onClick={()=>selectScope(run.id,{thread:thread.id,turn:turn.id})} aria-pressed={active&&scope.turn===turn.id}
            className={`absolute top-1.5 h-5 min-w-px rounded-sm border text-[10px] tabular-nums focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${turn.status==="completed"||turn.status==="running"?"border-accent-emerald-foreground/30 bg-accent-emerald text-accent-emerald-foreground":"border-error-foreground/30 bg-error-background text-error-foreground"}`}
            style={{left:`${position.left}%`,width:`${position.width}%`}}>{duration(turn.started,turn.ended)}</button>;
        })}
      </div>
    </div>;
  };
  return <section className="flex h-full min-w-0 flex-1 flex-col overflow-hidden bg-background text-foreground" aria-label="Graph agent activity">
    <header className="flex min-h-12 shrink-0 items-center justify-between gap-3 border-b px-4 py-3"><h1 className="text-sm font-semibold">Agents</h1>
      <Button variant="ghost" size="icon" aria-label="Refresh" onClick={()=>setRefresh(value=>value+1)}><IconComponent name="RefreshCcw" className="h-4 w-4"/></Button></header>
    <div className="min-w-0 flex-1 overflow-y-auto overflow-x-hidden">
    <div className="space-y-3 border-b px-4 py-3">
    <label className="flex flex-wrap items-center gap-3 text-sm">Graph execution <select className="max-w-full rounded-md border bg-background px-3 py-1.5 text-sm" value={execution} onChange={event=>{setExecution(event.target.value);setSelected("");setScope({})}}>
      {executions.map(id=><option key={id} value={id}>{time(runs.find(run=>run.execution===id)!.started)} · {id}</option>)}</select></label></div>
    <div className="min-w-0 p-4">
    {error&&<p role="alert" className="mb-4">{error}</p>}
    {!error&&!runs.length&&<p>No captured agent runs yet.</p>}
    {targetNode&&runs.length>0&&!visible.some(run=>run.node===targetNode)&&<p className="mb-4 text-sm text-muted-foreground">No captured activity for the selected node in this graph execution.</p>}
    {visible.length>0&&<><div className="overflow-x-auto rounded-md border border-border"><div data-testid="agent-timeline-axis" data-start={start} data-end={end} title="Execution bounds use runner receipt times; turn segments use captured provider timestamps." className="flex min-w-[900px] justify-between border-b bg-muted/40 py-2 pl-[372px] pr-3 text-xs tabular-nums text-muted-foreground"><span>{time(new Date(start).toISOString())}</span><span>{((end-start)/1000).toFixed(1)} seconds</span><span>{time(new Date(end).toISOString())}</span></div>
      {visible.map(run=>rowsByRun[run.id]?.length?rowsByRun[run.id].map(thread=>agentRow(run,thread)):<div key={run.id} data-testid="agent-timeline-row" className="grid min-w-[900px] grid-cols-[360px_1fr] border-b border-border"><button className="px-3 py-2 text-left text-sm font-medium" aria-label={`${label(run)} · ${run.status}`} onClick={()=>selectScope(run.id)}>{label(run)}</button><span className="px-3 py-2 text-xs text-muted-foreground">{details[run.id]?"No captured turns":"Loading captured turns…"}</span></div>)}
      </div>
      </>}
    {detail&&<article key={detail.run.id} className="mt-8 space-y-6" aria-label="Selected agent run">
      <SectionHeading>Selected agent run</SectionHeading>
      <nav aria-label="Activity selection" className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 text-sm">
        <button className="underline underline-offset-4" aria-current={!scope.thread?"page":undefined} onClick={()=>setScope({})}>All activity</button>
        {breadcrumbs.map(thread=><span key={thread.id} className="contents"><span aria-hidden="true">/</span><button className="max-w-full break-words underline underline-offset-4" aria-current={scope.thread===thread.id&&!scope.turn?"page":undefined} onClick={()=>setScope({thread:thread.id})}>{thread.title}</button></span>)}
        {currentTurn&&<span aria-current="page">/ Turn {currentConversation!.turns.indexOf(currentTurn)+1}</span>}
      </nav>
      {earlier&&<button className="text-xs underline underline-offset-4" onClick={()=>{setExecution(earlier.execution??"");selectScope(earlier.id)}}>Earlier run in this conversation · {time(earlier.started)}</button>}
      <section className="space-y-3 border bg-muted/30 px-4 py-3" aria-label="Invocation metadata">
        <div className="flex min-w-0 flex-wrap items-start justify-between gap-2"><h3 className="min-w-0 break-words text-lg font-semibold">{currentTurn?`Turn ${currentConversation!.turns.indexOf(currentTurn)+1} · ${currentConversation!.title}`:currentConversation?.id===detail.run.native_session?label(detail.run):currentConversation?.title??label(detail.run)}</h3><div className="flex items-center gap-2 text-xs text-muted-foreground">{statusBadge(selectedLane?.status??"unknown")}<span>{selectedLane&&duration(selectedLane.started,selectedLane.ended)}</span></div></div>
        <div className="flex flex-wrap items-start justify-between gap-3 text-xs text-muted-foreground"><p title={selectedLane?.started}>Started {selectedLane&&time(selectedLane.started)} · Provider {detail.run.provider??"codex-cli"} · Model {(scope.thread&&scope.thread!==detail.run.native_session?projection?.cost.model:detail.run.model)??"unconfirmed"} · Captured stream: {detail.run.stream_state}</p>
          <details><summary className="cursor-pointer">Node identity</summary><dl className="mt-2 grid gap-1 break-all"><dt>Node ID</dt><dd>{detail.run.node}</dd><dt>Name source</dt><dd>{detail.run.node_label?"Recorded when this invocation started":"Current canvas name; no name was recorded for this older invocation"}</dd></dl></details>
        </div>

      </section>
      {detail.run.reason&&<p className="text-sm" role="status">Capture note: {describeNodeFailure(detail.run.reason,undefined).title} <NodeErrorNotice message={detail.run.reason} context={{nodeId:detail.run.node,nodeLabel:label(detail.run)}}/></p>}
      {detail.truncated&&<p role="alert">This invocation exceeds the detail limit. The view is partial.</p>}
      <section className="min-w-0 space-y-4" aria-labelledby="agent-usage-heading">
        <SectionHeading id="agent-usage-heading" actions={<ActivityInfo label="Usage and cost details" text={`${projection!.usage===null?"Aggregate usage is incomplete. ":""}${projection!.cost_reason}. Cached input is part of input; reasoning is part of output. Charts show captured observations only.`}/>}>Usage and diagnostics</SectionHeading>
        <UsageCharts key={`usage:${selected}:${scope.thread??""}:${scope.turn??""}`} projection={projection!} scopeLabel={scopeLabel} running={!detail.truncated&&!detail.run.reason&&selectedLane?.status==="running"}/>
      </section>
      <RuntimeRecords key={`records:${selected}:${scope.thread??""}:${scope.turn??""}`} records={projection!.telemetry} coverage={projection!.telemetry_coverage} context={exportContext!}/>
      <Conversation key={`conversation:${selected}:${scope.thread??""}:${scope.turn??""}`} projection={projection!} context={exportContext!}/>
    </article>}
    </div></div>
  </section>;
}
