import { useEffect, useState } from "react";
import { api } from "@/controllers/API/api";
import { getBaseUrl } from "@/customization/utils/urls";

export type Commit = { commit_id: string; parent_commit: string | null; revision_id: string;
  message: string; created_at: string; editor: Record<string, string>; policy_ref?: Record<string, string> };
type History = { skill_id: string; selected_revision: string; commits: Commit[]; next: string | null };
type Comparison = { skill_id: string; base_commit: Commit; base_revision: string; current_revision: string;
  files: { path: string; status: string; binary: boolean }[]; patch: string };
const short = (identity: string) => identity.replace(/^sha256:/, "").slice(0, 8);

export default function CommitTree({ skillId, revision, selected, onSelect }: {
  skillId: string; revision: string; selected: string; onSelect: (commit: Commit) => void;
}) {
  const [items, setItems] = useState<Commit[]>([]);
  const [cursor, setCursor] = useState("");
  const [next, setNext] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [reload, setReload] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError(false);
    if (!cursor) setItems([]);
    const url = `${getBaseUrl()}laomedo/skills/${encodeURIComponent(skillId)}/${encodeURIComponent(revision)}/history`;
    api.get<History>(url, { params: { before: cursor }, signal: controller.signal }).then(({ data }) => {
      if (controller.signal.aborted) return;
      if (data.skill_id !== skillId || data.selected_revision !== revision || !Array.isArray(data.commits)) throw new Error();
      setItems((old) => cursor ? [...old, ...data.commits] : data.commits); setNext(data.next);
    }).catch(() => { if (!controller.signal.aborted) setError(true); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [skillId, revision, cursor, reload]);
  return <nav aria-label="Skill commit history" className="min-h-0 flex-1 overflow-auto border-t pt-3">
    <h3 className="mb-2 px-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Commits</h3>
    <ol>{items.map((item) => <li key={item.commit_id} className="relative">
      <button type="button" aria-label={`Compare revision: ${item.message}`} aria-pressed={selected === item.commit_id}
        title={`${item.commit_id}\n${item.message}\n${item.created_at}`}
        className={`relative flex w-full items-start gap-2 rounded px-2 py-2 text-left text-sm hover:bg-muted ${selected === item.commit_id ? "bg-muted" : ""}`}
        onClick={() => onSelect(item)}>
        {item.parent_commit && <span aria-hidden="true" className="pointer-events-none absolute bottom-[-12px] left-[14px] top-[18px] w-px bg-muted-foreground/50" />}
        <span aria-hidden="true" className="relative mt-1 block w-4 shrink-0 self-stretch">
          <span className="relative block h-[13px] w-[13px] rounded-full border-2 border-primary bg-background" />
        </span>
        <span className="min-w-0 flex-1"><span className="block break-words leading-snug">{item.message}</span>
          <span className="mt-1 block text-xs text-muted-foreground"><code>{short(item.commit_id)}</code>{" · "}
            <time dateTime={item.created_at}>{new Date(item.created_at).toLocaleDateString()}</time>
          </span>
          {item.revision_id === revision && <span className="text-xs text-muted-foreground">Same contents as current</span>}
        </span>
      </button>
    </li>)}</ol>
    {loading && <p role="status" className="p-2 text-sm">Loading commits…</p>}
    {error && <div role="alert" className="p-2 text-sm">History unavailable. <button type="button" onClick={() => setReload(reload + 1)}>Retry</button></div>}
    {!loading && !error && !items.length && <p className="p-2 text-sm">No operation history for this skill.</p>}
    {!loading && !error && next && <button type="button" className="m-2 text-sm underline" onClick={() => setCursor(next)}>Load older</button>}
  </nav>;
}

export function RevisionDiff({ skillId, revision, commit }: { skillId: string; revision: string; commit: Commit }) {
  const [comparison, setComparison] = useState<Comparison | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [reload, setReload] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setComparison(null); setError(false); setLoading(true);
    const url = `${getBaseUrl()}laomedo/skills/${encodeURIComponent(skillId)}/${encodeURIComponent(revision)}/compare/${encodeURIComponent(commit.commit_id)}`;
    api.get<Comparison>(url, { signal: controller.signal }).then(({ data }) => {
      if (controller.signal.aborted) return;
      if (data.skill_id !== skillId || data.current_revision !== revision ||
          data.base_commit.commit_id !== commit.commit_id || data.base_revision !== commit.revision_id) throw new Error();
      setComparison(data);
    }).catch(() => { if (!controller.signal.aborted) setError(true); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [skillId, revision, commit.commit_id, commit.revision_id, reload]);
  return <section aria-label="Revision comparison" className="min-h-0 min-w-0 flex-1 overflow-auto">
    <div className="sticky top-0 z-10 border-b bg-background px-4 py-3">
      <h3 className="font-semibold">{commit.message}</h3>
      <p className="mt-1 text-sm text-muted-foreground">Selected revision <code>{short(commit.revision_id)}</code> → Current <code>{short(revision)}</code></p>
    </div>
    {loading && <p role="status" className="p-4">Loading comparison…</p>}
    {error && <div role="alert" className="p-4">Comparison unavailable. <button type="button" onClick={() => setReload(reload + 1)}>Retry</button></div>}
    {comparison && <div className="p-4">
      <details className="mb-4 text-sm"><summary className="cursor-pointer">Revision details</summary>
        <dl className="mt-2 break-all">{Object.entries({ Commit: commit.commit_id, Parent: comparison.base_commit.parent_commit || "Import",
          "Selected tree": comparison.base_revision, "Current tree": comparison.current_revision, Timestamp: comparison.base_commit.created_at,
          ...comparison.base_commit.editor, Provenance: comparison.base_commit.editor.kind === "agent" ? "Backend-asserted; not independently runner-verified" : "Trusted operator/import",
          Policy: comparison.base_commit.policy_ref ? JSON.stringify(comparison.base_commit.policy_ref) : "Import" }).map(([key, value]) =>
          <div key={key}><dt className="inline font-semibold">{key}: </dt><dd className="inline">{value}</dd></div>)}</dl>
      </details>
      {!comparison.files.length ? <p data-testid="skill-no-differences">No differences from current revision.</p> : <>
        <p className="mb-2 text-sm">{comparison.files.length} changed {comparison.files.length === 1 ? "file" : "files"}</p>
        <ul className="mb-4 text-sm">{comparison.files.map((file) => <li key={file.path} className="break-all">
          <span className="mr-2 font-mono text-muted-foreground">{file.status === "added" ? "A" : file.status === "deleted" ? "D" : "M"}</span>
          {file.path}{file.binary ? " (binary)" : ""}</li>)}</ul>
        <pre className="overflow-auto whitespace-pre rounded border bg-muted/30 p-3 text-xs leading-5" data-testid="skill-commit-diff">
          {comparison.patch.split("\n").map((line, index) => <span key={index} className={`block min-h-5 ${line.startsWith("+") && !line.startsWith("+++") ? "bg-green-500/10 text-green-800 dark:text-green-300" : line.startsWith("-") && !line.startsWith("---") ? "bg-red-500/10 text-red-800 dark:text-red-300" : line.startsWith("@@") ? "text-blue-700 dark:text-blue-300" : ""}`}>{line || " "}</span>)}
        </pre>
      </>}
    </div>}
  </section>;
}
