import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import { api } from "@/controllers/API/api";
import { getBaseUrl } from "@/customization/utils/urls";
import BaseModal from "@/modals/baseModal";

export function nodeKind(type: string) { return type.match(/^ext:[^:]+:([^@]+)@.+$/)?.[1] ?? type; }

type Template = Record<string, { value?: unknown }> | undefined;
export function prSelection(template: Template) {
  const repository = typeof template?.repository_url?.value === "string" ? template.repository_url.value : "";
  const selected = typeof template?.pr_choice?.value === "string" ? template.pr_choice.value : "";
  const match = selected.match(/^#([1-9][0-9]*) /);
  const number = match ? Number(match[1]) : 0;
  const valid = /^https:\/\/github\.com\/[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+\/?$/.test(repository) && Number.isSafeInteger(number) && number > 0;
  return { repository_url: repository, pr_number: valid ? number : 0,
    labels: Array.isArray(template?.labels?.value) ? template.labels.value : [],
    state: typeof template?.state?.value === "string" ? template.state.value : "open",
    url: valid ? repository.replace(/\/$/, "") + "/pull/" + number : "" };
}
type PR = { repository: string; number: number; url: string; title: string; body: string; state: string; labels: string[]; updated_at: string; draft: boolean; merged: boolean; head: {branch: string; sha: string}; base: string };
type Snapshot = { schema_version: string; pr: PR; fetched_at: string };
const safeLink = (href: string | undefined) => href && /^https?:\/\//i.test(href) ? href : undefined;
export default function PRViewerModal({ template, open, setOpen }: { template: Template; open: boolean; setOpen: (open:boolean)=>void }) {
  const selection = prSelection(template);const key=JSON.stringify(selection);
  const [snapshot,setSnapshot]=useState<Snapshot|null>(null);const [loading,setLoading]=useState(false);const [error,setError]=useState("");const [reload,setReload]=useState(0);
  useEffect(()=>{
    const controller=new AbortController();setSnapshot(null);setError("");setLoading(false);
    if(!open)return()=>controller.abort();
    if(!selection.url){setError("Select a PR first.");return()=>controller.abort();}
    setLoading(true);
    api.post<Snapshot>(`${getBaseUrl()}laomedo/github-prs/inspect`,{repository_url:selection.repository_url,pr_number:selection.pr_number,labels:selection.labels,state:selection.state},{signal:controller.signal}).then(({data})=>{
      if(controller.signal.aborted)return;
      if(data.schema_version!=="laomedo.pr-inspection.v1" || data.pr.number!==selection.pr_number || data.pr.url.toLowerCase()!==selection.url.toLowerCase())throw Error("identity mismatch");
      setSnapshot(data);
    }).catch(()=>{if(!controller.signal.aborted)setError("PR unavailable. Check the current selection and connection.");}).finally(()=>{if(!controller.signal.aborted)setLoading(false);});
    return()=>controller.abort();
  },[open,key,reload]);
  return <BaseModal open={open} setOpen={setOpen} size="large">
    <BaseModal.Header description="Read the selected live PR. This does not run an agent or change GitHub."><span>PR viewer</span></BaseModal.Header>
    <BaseModal.Content>
      <nav className="mb-3 flex gap-3" aria-label="PR views">
        <button type="button" aria-current="page" className="rounded border px-3 py-2">PR viewer</button>
        {selection.url ? <a href={selection.url} target="_blank" rel="noopener noreferrer" className="rounded border px-3 py-2" data-testid="pr-open-browser">Open in GitHub</a> : <span aria-disabled="true" className="px-3 py-2">Open in GitHub</span>}
      </nav>
      {loading && <p role="status">Loading current PR...</p>}
      {error && <div role="alert">{error}</div>}
      {snapshot && <article data-testid="pr-viewer-content" className="break-words">
        <h2 className="mb-3 text-xl font-semibold">#{snapshot.pr.number} {snapshot.pr.title}</h2>
        <p className="mb-2">State: {snapshot.pr.state} | Labels: {snapshot.pr.labels.join(", ") || "None"}</p>
        <p className="mb-2">{snapshot.pr.head.branch} → {snapshot.pr.base} | Draft: {snapshot.pr.draft ? "Yes" : "No"} | Merged: {snapshot.pr.merged ? "Yes" : "No"}</p><p className="mb-4 text-sm text-muted-foreground">Updated: {snapshot.pr.updated_at} | Read: {snapshot.fetched_at}</p>
        <ReactMarkdown skipHtml components={{img:()=> <span>[Image omitted]</span>,a:({href,children})=>safeLink(href) ? <a href={safeLink(href)} target="_blank" rel="noopener noreferrer" className="underline">{children}</a> : <span>{children}</span>}}>{snapshot.pr.body}</ReactMarkdown>
      </article>}
      <button type="button" disabled={loading || !selection.url} className="mt-4 rounded border px-3 py-2" onClick={()=>setReload(reload+1)}>Refresh PR</button>
    </BaseModal.Content>
  </BaseModal>;
}
