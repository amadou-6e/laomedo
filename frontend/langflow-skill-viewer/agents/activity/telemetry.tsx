import { useMemo, useState } from "react";
import Fuse from "fuse.js";
import IconComponent from "@/components/common/genericIconComponent";
import { Button } from "@/components/ui/button";
import type { ExportContext } from "./models";
import { telemetryDocument, downloadActivity } from "./utils";
import { SectionHeading, ActivityInfo, JsonDisclosure } from "./components";

export function RuntimeRecords({records,coverage,context}:{records:Record<string,unknown>[];coverage:string;context?:ExportContext}) {
  const [query,setQuery]=useState("");
  const entries=useMemo(()=>records.map((record,index)=>({record,index,text:JSON.stringify(record)})),[records]);
  const search=useMemo(()=>new Fuse(entries,{keys:["text"],threshold:.35,ignoreLocation:true,minMatchCharLength:2}),[entries]);
  const visible=query.trim()?search.search(query.trim()).map(result=>result.item):entries;
  if(!records.length && (context?.provider==="claude"||context?.provider==="claude-code")) return null;
  return <section className="min-w-0 space-y-4" aria-label="OpenTelemetry">
    <SectionHeading actions={<><ActivityInfo label="OpenTelemetry capture details" text={`${coverage}. Runtime spans are not counted as agent invocations or token charges.`}/><Button variant="ghost" size="sm" className="h-7 gap-1.5 px-2 text-xs" aria-label="Export OpenTelemetry JSON" disabled={!visible.length} title={`Export ${visible.length} matching OpenTelemetry records`} onClick={()=>downloadActivity(telemetryDocument(visible.map(entry=>entry.record),coverage,context,query),`opentelemetry-${context?.run_id??"records"}.json`,"application/json")}><IconComponent name="Download" className="h-3.5 w-3.5"/>Export</Button></>}>OpenTelemetry</SectionHeading>
    <div className="flex min-w-0 items-center gap-3"><div className="relative min-w-0 flex-1"><IconComponent name="Search" className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted-foreground"/><input value={query} onChange={event=>setQuery(event.target.value)} aria-label="Search OpenTelemetry records" placeholder="Search records by name, thread, tool or metadata..." className="h-9 w-full rounded-md border bg-background pl-9 pr-16 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"/>{query&&<button type="button" onClick={()=>setQuery("")} className="absolute right-3 top-2 text-xs text-muted-foreground underline">Clear</button>}</div><span role="status" className="shrink-0 text-xs text-muted-foreground">{visible.length} of {records.length} records</span></div>
    <div role="region" aria-label="OpenTelemetry records" tabIndex={0} className="max-h-[min(360px,60vh)] overflow-y-auto [scrollbar-width:thin] [scrollbar-gutter:stable] divide-y rounded-md border focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">{visible.map(({record,index})=><div key={index} className="min-w-0 px-3 py-2"><JsonDisclosure label={`${index+1}. ${typeof record.name==="string"?record.name:`Runtime record ${index+1}`}${typeof record.signal==="string"?` / ${record.signal}`:""}`} value={record}/></div>)}{!visible.length&&<p className="p-3 text-sm text-muted-foreground">{records.length?"No matching records. Clear the search to show every record.":"No OpenTelemetry records captured."}</p>}</div>
  </section>;
}
