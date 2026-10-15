import { useEffect, useState } from "react";
import { api } from "@/controllers/API/api";
import { getBaseUrl } from "@/customization/utils/urls";

type Commit = { commit_id: string; parent_commit: string | null; revision_id: string;
  message: string; created_at: string; files: string[]; patch?: string;
  editor: Record<string, string>; policy_ref?: Record<string, string> };
type History = { skill_id: string; selected_revision: string; commits: Commit[]; next: string | null };

export default function SkillHistory({ skillId, revision }: { skillId: string; revision: string }) {
  const [items, setItems] = useState<Commit[]>([]);
  const [cursor, setCursor] = useState("");
  const [next, setNext] = useState<string | null>(null);
  const [selected, setSelected] = useState("");
  const [diff, setDiff] = useState<Commit | null>(null);
  const [loading, setLoading] = useState(true);
  const [diffLoading, setDiffLoading] = useState(false);
  const [error, setError] = useState("");
  const [diffError, setDiffError] = useState(false);
  const [reload, setReload] = useState(0);
  const [diffReload, setDiffReload] = useState(0);
  const base = `${getBaseUrl()}laomedo/skills/${encodeURIComponent(skillId)}/${encodeURIComponent(revision)}`;
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError("");
    if (!cursor) { setItems([]); setSelected(""); setDiff(null); }
    api.get<History>(`${base}/history`, { params: { before: cursor }, signal: controller.signal }).then(({ data }) => {
      if (controller.signal.aborted) return;
      if (data.skill_id !== skillId || data.selected_revision !== revision || !Array.isArray(data.commits)) throw new Error();
      setItems((old) => cursor ? [...old, ...data.commits] : data.commits); setNext(data.next);
    }).catch(() => { if (!controller.signal.aborted) setError("History unavailable."); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [base, cursor, reload, skillId, revision]);
  useEffect(() => {
    const controller = new AbortController();
    setDiff(null); setDiffError(false); setDiffLoading(Boolean(selected));
    if (selected) api.get<Commit>(`${base}/commits/${encodeURIComponent(selected)}`, { signal: controller.signal }).then(({ data }) => {
      if (controller.signal.aborted) return;
      if (data.commit_id !== selected) throw new Error();
      setDiff(data);
    }).catch(() => { if (!controller.signal.aborted) setDiffError(true); })
      .finally(() => { if (!controller.signal.aborted) setDiffLoading(false); });
    return () => controller.abort();
  }, [base, selected, diffReload]);
  return <div className="flex min-h-0 flex-1 gap-4" data-testid="skill-history">
    <nav aria-label="Skill commit history" className="w-80 shrink-0 overflow-auto border-r pr-3">
      {items.map((item) => <button key={item.commit_id} type="button" aria-label={`View diff: ${item.message}`}
        aria-pressed={selected === item.commit_id} className="mb-3 block w-full break-all rounded border p-3 text-left hover:bg-muted"
        onClick={() => setSelected(item.commit_id)}>
        <strong>{item.message}</strong><br /><time>{item.created_at}</time><br />
        <code>{item.commit_id}</code><br /><span>Tree: {item.revision_id}</span><br />
        <span>{item.files.join(", ") || "Import"}</span>
      </button>)}
      {loading && <p role="status">Loading history…</p>}
      {error && <div role="alert">{error} <button onClick={() => setReload(reload + 1)}>Retry</button></div>}
      {!loading && !error && !items.length && <p>No operation history for this skill.</p>}
      {!loading && !error && next && <button onClick={() => setCursor(next)}>Load older</button>}
    </nav>
    <section aria-label="Commit diff" className="min-w-0 flex-1 overflow-auto">
      {diffLoading && <p role="status">Loading diff…</p>}
      {diffError && <div role="alert">Diff unavailable. <button onClick={() => setDiffReload(diffReload + 1)}>Retry</button></div>}
      {!selected && <p>Select a commit to view its diff.</p>}
      {diff && <><h3 className="text-lg font-semibold">{diff.message}</h3>
        <dl className="mb-4 break-all text-sm">{Object.entries({ Commit: diff.commit_id, Parent: diff.parent_commit || "Import",
          Revision: diff.revision_id, Timestamp: diff.created_at, Files: diff.files.join(", "),
          ...diff.editor, Policy: diff.policy_ref ? JSON.stringify(diff.policy_ref) : "Import" }).map(([key, value]) =>
          <div key={key}><dt className="inline font-semibold">{key}: </dt><dd className="inline">{value}</dd></div>)}</dl>
        <pre className="overflow-auto whitespace-pre rounded bg-muted p-3 text-sm" data-testid="skill-commit-diff">{diff.patch || "No file changes (import)."}</pre>
      </>}
    </section>
  </div>;
}
