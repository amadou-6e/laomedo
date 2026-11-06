import Fuse from "fuse.js";
import { describeNodeFailure } from "@/components/laomedoErrors/nodeErrors";
import type { Lane, Projection, ExportContext, UsagePoint, ChartPoint, ActivityScope } from "./models";

export const time = (value:string) => new Date(value).toLocaleTimeString(undefined,{hour:"2-digit",minute:"2-digit",second:"2-digit"});

export const duration = (start:string,end:string|null) => `${Math.max(0,(Date.parse(end??new Date().toISOString())-Date.parse(start))/1000).toFixed(1)}s`;

export const messageText = (item:Record<string,unknown>|undefined,provider?:string) => {
  const text=typeof item?.text==="string"?item.text:
    item?.type==="userMessage"&&Array.isArray(item.content)?item.content.map(part=>typeof part?.text==="string"?part.text:"[Non-text content]").join("\n"):null;
  if(text!==null) {
    if(item?.type==="userMessage" && (provider==="claude"||provider==="claude-code")) {
      try {
        const envelope=JSON.parse(text);
        if(envelope && typeof envelope==="object" && !Array.isArray(envelope) &&
          typeof envelope.task==="string" && typeof envelope.workspace==="string" &&
          Array.isArray(envelope.skills) && Array.isArray(envelope.imported_artifacts) &&
          Object.keys(envelope).every(key=>["task","workspace","skills","imported_artifacts","output_requirements"].includes(key))) return envelope.task;
      } catch { /* Ordinary user prose and JSON remain unchanged. */ }
    }
    return text;
  }
  return null;
};

export function safeExportContext(context:ExportContext):ExportContext {
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
    ...items.map(lane=>{const value=lane.item??{},text=messageText(value,context.provider),speaker=value.type==="userMessage"?"User":lane.thread&&lane.thread!==context.native_session?"Subagent":"Agent";return `## ${text!==null?speaker:activityTitle(value)} · ${lane.started}\n\nThread: ${lane.thread??"Unknown"}${lane.turn?` · Turn: ${lane.turn}`:""}\n\n${text??fence(JSON.stringify(value,null,2))}`})].join("\n\n")+"\n";
}

export function downloadActivity(content:string,name:string,type:string) {
  const url=URL.createObjectURL(new Blob([content],{type}));
  const link=document.createElement("a");link.href=url;link.download=name;
  document.body.appendChild(link);
  try{link.click()}finally{link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000)}
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
  if(value.type==="dynamicToolCall")return value.tool==="mcp__laomedo__exec_command"?"Shell command":value.tool==="mcp__laomedo__github_operation"?"GitHub operation":typeof value.tool==="string"?value.tool:"Tool call";
  if(value.type==="toolCall"&&typeof value.toolName==="string")return value.toolName;
  return String(value.type??"Tool activity");
}

export const tokenSeries = [
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
