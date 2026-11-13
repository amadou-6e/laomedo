import { useMemo, useState } from "react";
import IconComponent from "@/components/common/genericIconComponent";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import type { Lane, Projection, ExportContext } from "./models";
import { time, duration, messageText, conversationMatches, conversationDocument, downloadActivity, activityTitle } from "./utils";
import { MessageMarkdown, SectionHeading, JsonDisclosure, MessageSource } from "./components";

export function Conversation({projection,context}:{projection:Projection;context:ExportContext}) {
  const [query,setQuery]=useState("");
  const [exportOpen,setExportOpen]=useState(false);
  const items=useMemo(()=>conversationMatches(projection.items,query),[projection.items,query]);
  const exportFile=(format:"md"|"json")=>{downloadActivity(conversationDocument(items,context,query,format),`conversation-${context.run_id}.${format}`,format==="md"?"text/markdown;charset=utf-8":"application/json");setExportOpen(false)};
  return <section aria-labelledby="agent-conversation-heading" className="min-w-0 space-y-4">
    <SectionHeading id="agent-conversation-heading" actions={<Popover open={exportOpen} onOpenChange={setExportOpen}><PopoverTrigger asChild><Button variant="ghost" size="sm" className="h-7 gap-1.5 px-2 text-xs" aria-label="Export conversation" disabled={!items.length} title={`Export ${items.length} matching conversation records`}><IconComponent name="Download" className="h-3.5 w-3.5"/>Export</Button></PopoverTrigger><PopoverContent align="end" className="w-44 p-1"><Button variant="ghost" className="w-full justify-start" onClick={()=>exportFile("md")}>Markdown (.md)</Button><Button ignoreTitleCase variant="ghost" className="w-full justify-start" onClick={()=>exportFile("json")}>JSON (.json)</Button></PopoverContent></Popover>}>Conversation</SectionHeading>
    <div className="flex min-w-0 items-center gap-3"><div className="relative min-w-0 flex-1"><IconComponent name="Search" className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted-foreground"/><input value={query} onChange={event=>setQuery(event.target.value)} aria-label="Search conversation" placeholder="Search messages and tools..." className="h-9 w-full rounded-md border bg-background pl-9 pr-16 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"/>{query&&<button type="button" onClick={()=>setQuery("")} className="absolute right-3 top-2 text-xs text-muted-foreground underline">Clear</button>}</div><span role="status" className="shrink-0 text-xs text-muted-foreground">{items.length} of {projection.items.length}</span></div>
    <div role="region" aria-label="Conversation messages and tools" tabIndex={0} className="min-w-0 space-y-5 px-3 pb-3 pr-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
      {!items.length&&<p className="text-sm text-muted-foreground">{projection.items.length?"No matching messages or tools.":"No messages or tool calls captured."}</p>}
      {items.map(item=><ActivityItem key={`${item.thread}:${item.id}`} lane={item} rootThread={context.native_session} provider={context.provider}/>)}
    </div>
  </section>;
}

export function ActivityItem({lane,rootThread,provider}:{lane:Lane;rootThread:string|null;provider?:string}) {
  const value=lane.item??{},message=messageText(value,provider),user=value.type==="userMessage";
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
