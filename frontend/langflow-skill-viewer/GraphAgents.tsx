import { useEffect, useState } from "react";
import { api } from "@/controllers/API/api";
import { getBaseUrl } from "@/customization/utils/urls";

type Run = {id:string;node:string;execution:string|null;started:string;ended:string|null;status:string;stream_state:string;reason?:string|null;runner_run_id:string|null;native_session:string|null;model:string|null;event_count:number};
type Lane = {id:string;thread?:string;turn?:string;started:string;ended:string|null;status?:string;item?:Record<string,unknown>;conflicting_receipts?:boolean};
type Cost = {amount:number|null;currency:string;basis:string;catalog_date:string;source:string|null};
type Projection = {turns:Lane[];items:Lane[];threads:{id:string;parent:string|null}[];usage:Record<string,number>|null;usage_points:{at:string;thread:string;usage:Record<string,number>;cost:Cost}[];clock:string;cost:Cost;cost_reason:string;telemetry:Record<string,unknown>[];telemetry_coverage:string};
type Detail = {run:Run;projection:Projection;truncated:boolean};
const time = (value:string) => new Date(value).toLocaleTimeString(undefined,{hour:"2-digit",minute:"2-digit",second:"2-digit"});
const duration = (start:string,end:string|null) => `${Math.max(0,(Date.parse(end??new Date().toISOString())-Date.parse(start))/1000).toFixed(1)}s`;
const messageText = (item:Record<string,unknown>|undefined) => {
  if(typeof item?.text==="string")return item.text;
  if(item?.type==="userMessage"&&Array.isArray(item.content))return item.content.map(part=>typeof part?.text==="string"?part.text:"[Non-text content]").join("\n");
  return null;
};

export function HighlightedJson({value}:{value:unknown}) {
  const tokens=(JSON.stringify(value,null,2)??"null").split(/("(?:\\.|[^"\\])*"\s*:|"(?:\\.|[^"\\])*"|\b(?:true|false|null)\b|-?\d+(?:\.\d+)?)/g);
  return <pre className="overflow-auto whitespace-pre-wrap break-words rounded bg-muted p-3 text-xs">{tokens.map((token,index)=><span key={index} className={token.startsWith('"')?(token.trimEnd().endsWith(":")?"text-blue-600 dark:text-blue-300":"text-emerald-700 dark:text-emerald-300"):/^(true|false|null|-?\d)/.test(token)?"text-violet-600 dark:text-violet-300":""}>{token}</span>)}</pre>;
}

export default function GraphAgents({flowId}:{flowId?:string}) {
  const [runs,setRuns]=useState<Run[]>([]),[execution,setExecution]=useState("");
  const [details,setDetails]=useState<Record<string,Detail>>({}),[selected,setSelected]=useState("");
  const [error,setError]=useState(""),[refresh,setRefresh]=useState(0);
  const base=`${getBaseUrl()}laomedo/agent-executions/${encodeURIComponent(flowId??"")}`;
  useEffect(()=>{setRuns([]);setExecution("");setDetails({});setSelected("")},[flowId]);
  useEffect(()=>{setDetails({})},[execution]);
  useEffect(()=>{
    if(!flowId)return;
    const controller=new AbortController();
    const load=async()=>{
      try {
        const {data}=await api.get<{runs:Run[]}>(base,{signal:controller.signal});
        if(controller.signal.aborted)return;
        setRuns(data.runs);setError("");
        setExecution(current=>data.runs.some(run=>run.execution===current)?current:data.runs.find(run=>run.execution)?.execution??"");
      } catch {if(!controller.signal.aborted)setError("Activity unavailable. Enable capture on the app host before running the graph.")}
    };
    void load();const timer=setInterval(load,2000);
    return()=>{controller.abort();clearInterval(timer)};
  },[base,flowId,refresh]);
  const visible=runs.filter(run=>run.execution===execution).sort((a,b)=>a.started.localeCompare(b.started));
  const signature=visible.map(run=>`${run.id}:${run.status}:${run.event_count}`).join(",");
  useEffect(()=>{
    const controller=new AbortController();
    void Promise.all(visible.map(async run=>{
      const {data}=await api.get<Detail>(`${base}/${encodeURIComponent(run.node)}/${run.id}`,{signal:controller.signal});
      if(!controller.signal.aborted)setDetails(current=>({...current,[run.id]:data}));
    })).catch(()=>{if(!controller.signal.aborted)setError("Some invocation details could not be loaded.")});
    return()=>controller.abort();
  },[base,execution,signature]);
  const start=Math.min(...visible.map(run=>Date.parse(run.started)));
  const end=Math.max(...visible.map(run=>Date.parse(run.ended??new Date().toISOString())));
  const span=Math.max(1000,end-start);
  const detail=details[selected];
  const executions=[...new Set(runs.map(run=>run.execution).filter((value):value is string=>Boolean(value)))];
  const bar=(lane:Lane,label:string,onClick?:()=>void)=><div key={lane.id} className="grid min-w-[700px] grid-cols-[220px_1fr] items-center gap-3 border-b py-2">
    <button className="truncate text-left text-sm hover:underline" onClick={onClick} title={label}>{label}</button>
    <div className="relative h-7 rounded bg-muted"><button aria-label={`${label}, ${duration(lane.started,lane.ended)}`} title={`${lane.started} → ${lane.ended??"running"}`} onClick={onClick}
      className={`absolute top-1 h-5 min-w-2 rounded text-[10px] text-white ${lane.status==="completed"?"bg-emerald-600":lane.status==="running"?"bg-blue-600":"bg-amber-700"}`}
      style={{left:`${Math.max(0,(Date.parse(lane.started)-start)/span*100)}%`,width:`${Math.max(.5,Math.min(100,(Date.parse(lane.ended??new Date().toISOString())-Date.parse(lane.started))/span*100))}%`}}>
      {duration(lane.started,lane.ended)}</button></div></div>;
  return <section className="h-full w-full overflow-auto p-6" aria-label="Graph agent activity">
    <div className="mb-5 flex flex-wrap items-center justify-between gap-3"><div><h1 className="text-xl font-semibold">Agents</h1><p className="text-sm text-muted-foreground">Agent activity across this graph, grouped by execution.</p></div>
      <button className="rounded border px-3 py-2" onClick={()=>setRefresh(value=>value+1)}>Refresh</button></div>
    <label className="mb-5 block text-sm">Graph execution <select className="ml-3 max-w-full rounded border bg-background p-2" value={execution} onChange={event=>{setExecution(event.target.value);setSelected("")}}>
      {executions.map(id=><option key={id} value={id}>{time(runs.find(run=>run.execution===id)!.started)} · {id}</option>)}</select></label>
    {error&&<p role="alert" className="mb-4">{error}</p>}
    {!error&&!runs.length&&<p>No captured agent runs yet.</p>}
    {visible.length>0&&<><div className="overflow-x-auto rounded border p-4"><div className="mb-2 flex justify-between pl-[232px] text-xs text-muted-foreground"><span>{time(new Date(start).toISOString())}</span><span>{((end-start)/1000).toFixed(1)} seconds</span><span>{time(new Date(end).toISOString())}</span></div>
      {visible.map(run=><div key={run.id}>{bar({...run,id:run.id},`${run.node} · ${run.status}`,()=>setSelected(run.id))}
        {details[run.id]?.projection.turns.map(turn=>bar(turn,`↳ ${turn.thread===run.native_session?"Turn":"Subagent turn"} ${turn.id.slice(0,8)} · ${turn.status}`,()=>setSelected(run.id)))}</div>)}</div>
      <p className="my-2 text-xs text-muted-foreground">Bars use runner receipt times. Viewing activity never starts an agent. Select an invocation to inspect it.</p></>}
    {detail&&<article className="mt-6 space-y-4"><h2 className="font-semibold">{detail.run.node} · {detail.run.status}</h2>
      <p className="text-sm">{time(detail.run.started)} · {duration(detail.run.started,detail.run.ended)} · {detail.run.model??"Model unconfirmed"} · Captured stream: {detail.run.stream_state}</p>
      {detail.run.reason&&<p className="text-sm" role="status">Capture note: {detail.run.reason.replaceAll("_"," ")}</p>}
      <div className="flex flex-wrap gap-6 rounded border p-4">{["inputTokens","cachedInputTokens","outputTokens","reasoningOutputTokens"].map(key=><div key={key}><div className="text-xs text-muted-foreground">{key.replace(/Tokens$/, " tokens").replace(/([A-Z])/g," $1")}</div><div className="text-lg font-semibold">{detail.projection.usage?.[key]?.toLocaleString()??"Unknown"}</div></div>)}<div><div className="text-xs text-muted-foreground">API equivalent estimate</div><div className="text-lg font-semibold">{detail.projection.cost.amount===null?"Unknown":`$${detail.projection.cost.amount.toFixed(6)}`}</div></div></div>
      <p className="text-xs text-muted-foreground">{detail.projection.cost_reason} Cached input is part of input; reasoning is part of output.</p>
      {detail.truncated&&<p role="alert">This invocation exceeds the detail limit. The view is partial.</p>}
      <h3 className="font-semibold">Messages and tools</h3>
      {detail.projection.items.map(item=><div key={`${item.thread}:${item.id}`} className="rounded border p-4"><div className="mb-2 flex justify-between text-sm"><strong>{String(item.item?.type??"Item")}</strong><span title={item.started}>{time(item.started)} · {duration(item.started,item.ended)}</span></div>
        {item.conflicting_receipts&&<p>Conflicting native receipts retained.</p>}
        {messageText(item.item)!==null?<p className="whitespace-pre-wrap break-words">{messageText(item.item)}</p>:<HighlightedJson value={item.item}/>}</div>)}
      <details><summary className="cursor-pointer">Tokens and API-equivalent cost over time</summary><table className="my-3 w-full text-left text-sm"><thead><tr><th>Observed</th><th>Thread</th><th>Input</th><th>Cached input</th><th>Output</th><th>Estimate (USD)</th></tr></thead><tbody>{detail.projection.usage_points.map((point,index)=><tr key={index}><td title={point.at}>{time(point.at)}</td><td>{point.thread.slice(0,8)}</td>{["inputTokens","cachedInputTokens","outputTokens"].map(key=><td key={key}>{point.usage[key]?.toLocaleString()??"Unknown"}</td>)}<td>{point.cost?.amount==null?"Unknown":`$${point.cost.amount.toFixed(6)}`}</td></tr>)}</tbody></table></details>
      <details><summary className="cursor-pointer">Thread and subagent links</summary><HighlightedJson value={detail.projection.threads}/></details>
      <details><summary className="cursor-pointer">OpenTelemetry · {detail.projection.telemetry.length} records</summary><p className="my-2 text-sm">{detail.projection.telemetry_coverage}. Runtime spans are not counted as agent invocations or token charges.</p>{detail.projection.telemetry.slice(0,50).map((record,index)=><HighlightedJson key={index} value={record}/>)}{detail.projection.telemetry.length>50&&<p>Showing the first 50 runtime records.</p>}</details>
    </article>}
  </section>;
}
