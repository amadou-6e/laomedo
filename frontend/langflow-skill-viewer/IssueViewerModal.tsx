import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import { api } from "@/controllers/API/api";
import { getBaseUrl } from "@/customization/utils/urls";
import BaseModal from "@/modals/baseModal";

export function nodeKind(type: string) { return type.match(/^ext:[^:]+:([^@]+)@.+$/)?.[1] ?? type; }

type Template = Record<string, { value?: unknown }> | undefined;
export function issueSelection(template: Template) {
  const repository = typeof template?.repository_url?.value === "string" ? template.repository_url.value : "";
  const selected = typeof template?.issue_choice?.value === "string" ? template.issue_choice.value : "";
  const match = selected.match(/^#([1-9][0-9]*) /);
  const number = match ? Number(match[1]) : 0;
  const valid = /^https:\/\/github\.com\/[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+\/?$/.test(repository) && Number.isSafeInteger(number) && number > 0;
  return { repository_url: repository, issue_number: valid ? number : 0,
    labels: Array.isArray(template?.labels?.value) ? template.labels.value : [],
    state: typeof template?.state?.value === "string" ? template.state.value : "open",
    url: valid ? repository.replace(/\/$/, "") + "/issues/" + number : "" };
}
type Issue = { repository: string; number: number; url: string; title: string; body: string; state: string; labels: string[]; updated_at: string };
type Snapshot = { schema_version: string; issue: Issue; fetched_at: string };
const safeLink = (href: string | undefined) => href && /^https?:\/\//i.test(href) ? href : undefined;
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
    <BaseModal.Content className="min-h-0">
      {loading && <p role="status">Loading current issue...</p>}
      {error && <div role="alert">{error}</div>}
      {snapshot && <article data-testid="issue-viewer-content" className="break-words">
        <header className="mb-6 border-b pb-5">
          <p className="mb-2 text-sm text-muted-foreground">{snapshot.issue.repository}</p>
          <h2 className="mb-4 text-2xl font-semibold leading-tight">{snapshot.issue.title} <span className="font-normal text-muted-foreground">#{snapshot.issue.number}</span></h2>
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-full bg-secondary px-3 py-1 text-sm font-semibold">{snapshot.issue.state === "open" ? "Open" : "Closed"}</span>
            {snapshot.issue.labels.map(label => <span key={label} className="rounded-full border px-3 py-1 text-sm">{label}</span>)}
          </div>
        </header>
        <section aria-label="Issue description" className="rounded-lg border">
          <div className="border-b bg-muted px-5 py-3 text-sm text-muted-foreground">
            Updated <time dateTime={snapshot.issue.updated_at}>{new Date(snapshot.issue.updated_at).toLocaleString()}</time>
          </div>
          <div className="space-y-4 px-5 py-5 text-base leading-7">
            <ReactMarkdown skipHtml components={{
              img:()=> <span>[Image omitted]</span>,
              a:({href,children})=>safeLink(href) ? <a href={safeLink(href)} target="_blank" rel="noopener noreferrer" className="underline">{children}</a> : <span>{children}</span>,
              h1:({children})=><h3 className="border-b pb-2 text-2xl font-semibold">{children}</h3>,
              h2:({children})=><h3 className="border-b pb-2 text-xl font-semibold">{children}</h3>,
              h3:({children})=><h4 className="text-lg font-semibold">{children}</h4>,
              ul:({children})=><ul className="list-disc space-y-1 pl-6">{children}</ul>,
              ol:({children})=><ol className="list-decimal space-y-1 pl-6">{children}</ol>,
              blockquote:({children})=><blockquote className="border-l-4 pl-4 text-muted-foreground">{children}</blockquote>,
              pre:({children})=><pre className="overflow-x-auto rounded-md bg-muted p-4 text-sm">{children}</pre>,
              code:({children})=><code className="rounded bg-muted px-1 text-sm">{children}</code>,
            }}>{snapshot.issue.body || "No description provided."}</ReactMarkdown>
          </div>
        </section>
        <p className="mt-3 text-xs text-muted-foreground">Read <time dateTime={snapshot.fetched_at}>{new Date(snapshot.fetched_at).toLocaleString()}</time></p>
      </article>}
    </BaseModal.Content>
    <BaseModal.Footer>
      <div className="flex flex-wrap justify-end gap-3 border-t pt-4" data-testid="issue-viewer-actions">
        {selection.url ? <a href={selection.url} target="_blank" rel="noopener noreferrer" className="rounded border px-3 py-2 text-sm" data-testid="issue-open-browser">Open in GitHub</a> : <span aria-disabled="true" className="px-3 py-2 text-sm text-muted-foreground">Open in GitHub</span>}
        <button type="button" disabled={loading || !selection.url} className="rounded border px-3 py-2 text-sm disabled:opacity-50" onClick={()=>setReload(value=>value+1)}>Refresh issue</button>
      </div>
    </BaseModal.Footer>
  </BaseModal>;
}
