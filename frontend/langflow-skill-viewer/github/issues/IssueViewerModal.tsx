import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import { api } from "@/controllers/API/api";
import { getBaseUrl } from "@/customization/utils/urls";
import BaseModal from "@/modals/baseModal";
import type { NodeTemplate as Template } from "../models";
import type { Snapshot } from "./models";
import { issueSelection, safeLink } from "./selection";

export default function IssueViewerModal({ template, open, setOpen }: { template: Template; open: boolean; setOpen: (open:boolean)=>void }) {
  const selection = issueSelection(template);const key=JSON.stringify(selection);
  const [snapshot,setSnapshot]=useState<Snapshot|null>(null);const [loading,setLoading]=useState(false);const [error,setError]=useState("");const [reload,setReload]=useState(0);
  useEffect(()=>{
    const controller=new AbortController();setSnapshot(null);setError("");setLoading(false);
    if(!open)return()=>controller.abort();
    if(!selection.url){setError("Select an issue first.");return()=>controller.abort();}
    setLoading(true);
    api.post<Snapshot>(`${getBaseUrl()}laomedo/github-issues/inspect`,{repository_url:selection.repository_url,issue_number:selection.issue_number,labels:selection.labels,state:selection.state},{signal:controller.signal}).then(({data})=>{
      if(controller.signal.aborted)return;
      if(data.schema_version!=="laomedo.issue-inspection.v1" || data.issue.number!==selection.issue_number || data.issue.url.toLowerCase()!==selection.url.toLowerCase())throw Error("identity mismatch");
      setSnapshot(data);
    }).catch(()=>{if(!controller.signal.aborted)setError("Issue unavailable. Check the current selection and connection.");}).finally(()=>{if(!controller.signal.aborted)setLoading(false);});
    return()=>controller.abort();
  },[open,key,reload]);
  return <BaseModal open={open} setOpen={setOpen} size="large">
    <BaseModal.Header description="Read the selected live issue. This does not run an agent or change GitHub."><span>Issue viewer</span></BaseModal.Header>
    <BaseModal.Content>
      <nav className="mb-3 flex gap-3" aria-label="Issue views">
        <button type="button" aria-current="page" className="rounded border px-3 py-2">Issue viewer</button>
        {selection.url ? <a href={selection.url} target="_blank" rel="noopener noreferrer" className="rounded border px-3 py-2" data-testid="issue-open-browser">Open in GitHub</a> : <span aria-disabled="true" className="px-3 py-2">Open in GitHub</span>}
      </nav>
      {loading && <p role="status">Loading current issue...</p>}
      {error && <div role="alert">{error}</div>}
      {snapshot && <article data-testid="issue-viewer-content" className="break-words">
        <h2 className="mb-3 text-xl font-semibold">#{snapshot.issue.number} {snapshot.issue.title}</h2>
        <p className="mb-2">State: {snapshot.issue.state} | Labels: {snapshot.issue.labels.join(", ") || "None"}</p>
        <p className="mb-4 text-sm text-muted-foreground">Updated: {snapshot.issue.updated_at} | Read: {snapshot.fetched_at}</p>
        <ReactMarkdown skipHtml components={{img:()=> <span>[Image omitted]</span>,a:({href,children})=>safeLink(href) ? <a href={safeLink(href)} target="_blank" rel="noopener noreferrer" className="underline">{children}</a> : <span>{children}</span>}}>{snapshot.issue.body}</ReactMarkdown>
      </article>}
      <button type="button" disabled={loading || !selection.url} className="mt-4 rounded border px-3 py-2" onClick={()=>setReload(reload+1)}>Refresh issue</button>
    </BaseModal.Content>
  </BaseModal>;
}
