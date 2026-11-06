import { useState } from "react";
import Markdown from "react-markdown";
import IconComponent from "@/components/common/genericIconComponent";
import SimplifiedCodeTabComponent from "@/components/core/codeTabsComponent";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";

export function HighlightedJson({value}:{value:unknown}) {
  return <SimplifiedCodeTabComponent code={JSON.stringify(value,null,2)??"null"} language="json"/>;
}

// The upstream code font rule is !important; override it locally for transcript code.
export function MessageMarkdown({text}:{text:string}) {
  return <Markdown skipHtml disallowedElements={["img"]} className="prose prose-sm max-w-none break-words dark:prose-invert prose-code:before:content-none prose-code:after:content-none prose-code:!font-mono prose-code:font-normal [&_pre]:overflow-x-auto [&_pre]:whitespace-pre-wrap [&_code]:break-words" components={{code:({node,...props})=><code {...props} style={{fontFamily:"ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",fontWeight:400}}/>,a:({node,...props})=><a {...props} target="_blank" rel="noopener noreferrer"/>}}>{text}</Markdown>;
}

export function SectionHeading({children,id,actions}:{children:React.ReactNode;id?:string;actions?:React.ReactNode}) {
  return <div className="flex min-w-0 items-center gap-5"><h2 id={id} className="shrink-0 text-xs font-semibold uppercase tracking-wide text-muted-foreground">{children}</h2><div className="h-px min-w-4 flex-1 bg-border"/>{actions&&<div className="flex shrink-0 items-center gap-2">{actions}</div>}</div>;
}

export function ActivityInfo({label,text}:{label:string;text:string}) {
  return <Popover><PopoverTrigger asChild><Button variant="ghost" size="icon" className="h-6 w-6 text-muted-foreground" aria-label={label}><IconComponent name="Info" className="h-3.5 w-3.5"/></Button></PopoverTrigger><PopoverContent className="max-w-[calc(100vw-2rem)] text-xs" align="end">{text}</PopoverContent></Popover>;
}

export function JsonDisclosure({label,value,className}:{label:string;value:unknown;className?:string}) {
  const [open,setOpen]=useState(false);
  return <details className={className} onToggle={event=>setOpen(event.currentTarget.open)}><summary className="cursor-pointer text-xs text-muted-foreground">{label}</summary>{open&&<div className="mt-2 min-w-0"><HighlightedJson value={value}/></div>}</details>;
}

export function MessageSource({value}:{value:unknown}) {
  const [open,setOpen]=useState(false);
  return <Popover open={open} onOpenChange={setOpen}>
    <PopoverTrigger asChild><Button variant="ghost" size="icon" className="h-5 w-5 shrink-0 text-muted-foreground" title="View message source" aria-label="View message source"><IconComponent name="Code" className="h-3.5 w-3.5"/></Button></PopoverTrigger>
    <PopoverContent align="end" collisionPadding={12} aria-label="Message source" className="max-h-[70vh] w-[min(520px,calc(100vw-2rem))] overflow-auto p-3" onKeyDown={event=>event.stopPropagation()}>
      <div className="flex items-center justify-between gap-3"><h3 className="text-sm font-medium">Message source</h3><Button variant="ghost" size="icon" className="h-6 w-6" aria-label="Close message source" onClick={()=>setOpen(false)}><IconComponent name="X" className="h-3.5 w-3.5"/></Button></div>
      {open&&<HighlightedJson value={value}/>}
    </PopoverContent>
  </Popover>;
}
