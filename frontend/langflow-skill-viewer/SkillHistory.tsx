import { useEffect, useState } from "react";
import { api } from "@/controllers/API/api";
import { getBaseUrl } from "@/customization/utils/urls";
import SkillFileDiff from "./SkillFileDiff";

export type Commit = { commit_id: string; parent_commit: string | null; revision_id: string;
  message: string; created_at: string; editor: Record<string, string>; policy_ref?: Record<string, string> };
type History = { skill_id: string; selected_revision: string; commits: Commit[]; next: string | null };
export type SkillFile = { path: string; bytes: number; file_hash: string; kind: "text" | "binary"; text: string | null; image_data_url?: string };
export type Snapshot = { schema_version: string; skill_id: string; revision_id: string; tree_hash: string; files: SkillFile[] };
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

export function RevisionDiff({ skillId, revision, commit, path, current, onFiles }: {
  skillId: string; revision: string; commit: Commit; path: string; current?: SkillFile;
  onFiles: (files: SkillFile[]) => void;
}) {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [reload, setReload] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setSnapshot(null); setError(false); setLoading(true); onFiles([]);
    const url = `${getBaseUrl()}laomedo/skills/${encodeURIComponent(skillId)}/${encodeURIComponent(commit.revision_id)}`;
    api.get<Snapshot>(url, { signal: controller.signal }).then(({ data }) => {
      if (controller.signal.aborted) return;
      if (data.schema_version !== "laomedo.skill-inspection.v1" || data.skill_id !== skillId ||
          data.revision_id !== commit.revision_id || data.tree_hash !== commit.revision_id) throw new Error();
      setSnapshot(data); onFiles(data.files);
    }).catch(() => { if (!controller.signal.aborted) setError(true); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [skillId, revision, commit.commit_id, commit.revision_id, reload, onFiles]);
  const original = snapshot?.files.find((file) => file.path === path);
  const ready = snapshot && snapshot.skill_id === skillId && snapshot.revision_id === commit.revision_id;
  return <section aria-label="Revision comparison" className="flex min-h-0 min-w-0 flex-1 flex-col">
    <div className="shrink-0 border-b bg-background px-4 py-2">
      <h3 className="break-all font-semibold">{path || "Select a file"}</h3>
      <p className="mt-1 text-sm text-muted-foreground">Selected revision <code>{short(commit.revision_id)}</code> &rarr; Current <code>{short(revision)}</code></p>
      <details className="mt-1 text-xs"><summary className="cursor-pointer">{commit.message} · Revision details</summary>
        <dl className="max-h-28 overflow-auto break-all">{Object.entries({ Commit: commit.commit_id, Parent: commit.parent_commit || "Import",
          Timestamp: commit.created_at, ...commit.editor,
          Provenance: commit.editor.kind === "agent" ? "Backend-asserted; not independently runner-verified" : "Trusted operator/import",
          Policy: commit.policy_ref ? JSON.stringify(commit.policy_ref) : "Import" }).map(([key, value]) =>
          <div key={key}><dt className="inline font-semibold">{key}: </dt><dd className="inline">{value}</dd></div>)}</dl>
      </details>
    </div>
    {loading && <p role="status" className="p-4">Loading comparison…</p>}
    {error && <div role="alert" className="p-4">Comparison unavailable. <button type="button" onClick={() => setReload(reload + 1)}>Retry</button></div>}
    {ready && <SkillFileDiff key={`${commit.commit_id}:${path}`} path={path} original={original} current={current} />}
  </section>;
}
