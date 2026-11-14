import { useEffect, useId, useMemo, useState } from "react";
import type { Projection, ChartPoint } from "./models";
import { time, tokenSeries, aggregateUsagePoints } from "./utils";

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
