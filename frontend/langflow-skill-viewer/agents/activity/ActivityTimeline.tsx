import { useEffect, useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import type { ActivityScope, Detail, Lane, Run } from "./models";
import { conversationRows, duration, time, turnPosition } from "./utils";
import { ProviderIcon } from "./ProviderIcon";

export function ActivityTimeline({runs,details,selected,scope,start,end,label,onSelect}:{runs:Run[];details:Record<string,Detail>;selected:string;scope:ActivityScope;start:number;end:number;label:(run:Run)=>string;onSelect:(run:string,scope?:ActivityScope)=>void}) {
  const [collapsed,setCollapsed]=useState<Set<string>>(new Set());
  const execution=runs[0]?.execution;
  useEffect(()=>setCollapsed(new Set()),[execution]);
  const selection="bg-primary/10 shadow-[inset_2px_0_0_hsl(var(--primary))]";
  const rowClass="grid w-full grid-cols-[minmax(220px,38%)_1fr] items-center border-t border-border/60 text-left transition-colors hover:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring";
  const segments=(turns:Lane[],active=false)=><span className="relative mx-3 block h-8" aria-hidden="true">{turns.map(turn=>{
    const position=turnPosition(turn,start,end);
    return position&&<span key={turn.id} data-timing-segment className={`absolute top-2 block h-4 min-w-px rounded-sm border text-center text-[10px] tabular-nums ${active?"border-primary/70":"border-accent-emerald-foreground/30"} ${turn.status==="completed"||turn.status==="running"?"bg-accent-emerald text-accent-emerald-foreground":"border-error-foreground/30 bg-error-background text-error-foreground"}`} style={{left:`${position.left}%`,width:`${position.width}%`}}>{duration(turn.started,turn.ended)}</span>;
  })}</span>;
  const badge=(status:string)=><Badge size="tag" variant={status==="completed"?"successStatic":status==="running"||status==="waiting"?"secondaryStatic":"errorStatic"}>{status==="waiting"?"starting":status}</Badge>;
  return <div className="overflow-x-auto" aria-label="Agent run timeline">
    <div className="min-w-[640px]">
      <div data-testid="agent-timeline-axis" data-start={start} data-end={end} title="Execution bounds use runner receipt times; turn segments use captured provider timestamps." className="grid grid-cols-[minmax(220px,38%)_1fr] items-center pb-2 text-xs text-muted-foreground"><h2 className="px-3 font-medium">Agent runs</h2><div className="flex justify-between px-3 tabular-nums"><span>{time(new Date(start).toISOString())}</span><span>{((end-start)/1000).toFixed(1)} seconds</span><span>{time(new Date(end).toISOString())}</span></div></div>
      {runs.map(run=>{
        const rows=details[run.id]?conversationRows(details[run.id].projection,run.native_session):[];
        if(!rows.length)return <button key={run.id} data-testid="agent-timeline-row" className={`${rowClass} ${selected===run.id?selection:""}`} aria-label={`${label(run)} \u00b7 ${run.status}`} aria-pressed={selected===run.id} onClick={()=>onSelect(run.id)}><span className="flex items-center gap-2 px-3 py-3 text-sm font-medium"><ProviderIcon provider={run.provider}/>{label(run)}{badge(run.status)}</span><span className="px-3 text-xs text-muted-foreground">{details[run.id]?(run.status==="running"?"starting":"No captured turns"):"Loading captured turns\u2026"}</span></button>;
        const byId=new Map(rows.map(row=>[row.id,row]));
        const hidden=(thread:typeof rows[number])=>{
          const seen=new Set<string>();let parent=thread.parent;
          while(parent&&!seen.has(parent)){seen.add(parent);if(collapsed.has(`${run.id}:${parent}`))return true;parent=byId.get(parent)?.parent??null}return false;
        };
        return rows.filter(thread=>!hidden(thread)).map(thread=>{
          const isRoot=thread.id===run.native_session,name=isRoot?label(run):thread.title;
          const key=`${run.id}:${thread.id}`,expanded=!collapsed.has(key);
          const active=selected===run.id&&(scope.thread===thread.id||(!scope.thread&&isRoot));
          const status=thread.lane?.status??(isRoot&&run.status==="running"?"waiting":"unknown");
          const rowLabel=isRoot?`${name} \u00b7 ${status==="waiting"?"starting":run.status}`:`${name} \u00b7 ${thread.turns.length} ${thread.turns.length===1?"turn":"turns"} \u00b7 ${status}`;
          const expandable=thread.turns.length>0||rows.some(child=>child.parent===thread.id);
          const toggle=()=>{
            setCollapsed(current=>{const next=new Set(current);if(expanded)next.add(key);else next.delete(key);return next});
            if(expanded&&selected===run.id){let target=scope.thread;const seen=new Set<string>();while(target&&!seen.has(target)){seen.add(target);if(target===thread.id){onSelect(run.id,{thread:thread.id});break}target=byId.get(target)?.parent??undefined}}
          };
          return <div key={key}>
            <div className="relative" data-testid="agent-timeline-row" data-thread={thread.id}>
              {expandable&&<button type="button" className="absolute inset-y-0 z-10 flex w-7 items-center justify-center text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" style={{left:Math.min(thread.depth,8)*16}} aria-label={`${expanded?"Collapse":"Expand"} ${name}`} aria-expanded={expanded} onClick={toggle}>{expanded?<ChevronDown className="h-3 w-3"/>:<ChevronRight className="h-3 w-3"/>}</button>}
              <button type="button" className={`${rowClass} ${active&&!scope.turn?selection:""}`} aria-label={rowLabel} aria-pressed={active&&!scope.turn} onClick={()=>onSelect(run.id,{thread:thread.id})}><span className="flex min-w-0 items-center gap-2 py-3 pr-3 text-sm font-medium" style={{paddingLeft:28+Math.min(thread.depth,8)*16}}><ProviderIcon provider={isRoot?run.provider:undefined}/><span className="min-w-0 flex-1 break-words">{name}<span className="ml-2 whitespace-nowrap text-xs font-normal text-muted-foreground">{thread.turns.length} {thread.turns.length===1?"turn":"turns"}</span></span>{badge(status)}</span>{segments(thread.turns)}</button>
            </div>
            {expanded&&thread.turns.map((turn,index)=>{
              const chosen=active&&scope.turn===turn.id;
              return <button type="button" key={turn.id} data-testid="agent-turn-bar" className={`${rowClass} ${chosen?selection:""}`} aria-label={`Turn ${index+1} \u00b7 ${thread.title} \u00b7 ${turn.status}, ${duration(turn.started,turn.ended)}`} aria-pressed={chosen} onClick={()=>onSelect(run.id,{thread:thread.id,turn:turn.id})}><span className="flex items-center gap-2 py-2 pr-3 text-xs text-muted-foreground" style={{paddingLeft:44+Math.min(thread.depth,8)*16}}>Turn {index+1}{turn.status!=="completed"&&badge(turn.status??"unknown")}</span>{segments([turn],chosen)}</button>;
            })}
          </div>;
        });
      })}
    </div>
  </div>;
}
