import { useEffect, useState } from "react";
import { api } from "@/controllers/API/api";
import { getBaseUrl } from "@/customization/utils/urls";
import SkillFileDiff from "./SkillFileDiff";
import type { Snapshot } from "./SkillHistory";
import type { SkillEditing } from "./SkillEditing";
import ErrorPopup from "@/components/laomedoErrors/ErrorPopup";

export default function SkillPublication({ snapshot, expectedLatest, editor, onClose }: {
  snapshot: Snapshot; expectedLatest: string; editor: SkillEditing; onClose: () => void;
}) {
  const [base, setBase] = useState<Snapshot | null>(null);
  const [error, setError] = useState(false);
  const [reload, setReload] = useState(0);
  const [showError, setShowError] = useState(false);
  const [path, setPath] = useState("");
  useEffect(() => {
    const controller = new AbortController(); setError(false); setBase(null);
    api.get<Snapshot>(`${getBaseUrl()}laomedo/skills/${encodeURIComponent(snapshot.skill_id)}/${encodeURIComponent(expectedLatest)}`, { signal: controller.signal }).then(({ data }) => {
      if (controller.signal.aborted) return;
      if (data.schema_version !== "laomedo.skill-inspection.v1" || data.skill_id !== snapshot.skill_id || data.revision_id !== expectedLatest || data.tree_hash !== expectedLatest) throw Error();
      setBase(data);
    }).catch(() => { if (!controller.signal.aborted) { setError(true); setShowError(true); } });
    return () => controller.abort();
  }, [snapshot.skill_id, expectedLatest, reload]);
  const paths = [...new Set([...(base?.files || []).map((file) => file.path), ...snapshot.files.map((file) => file.path)])].sort()
    .filter((name) => base?.files.find((file) => file.path === name)?.file_hash !== snapshot.files.find((file) => file.path === name)?.file_hash);
  const selected = paths.includes(path) ? path : paths[0] || "";
  return <section className="flex min-h-0 flex-1 flex-col" aria-label="Review registry publication">
    <div className="shrink-0 border-b py-2 text-sm">
      <h3 className="font-semibold">Review publication</h3>
      <p>Registry current <code title={expectedLatest}>{expectedLatest.slice(7, 15)}</code> → Candidate <code title={snapshot.revision_id}>{snapshot.revision_id.slice(7, 15)}</code></p>
    </div>
    {error ? <p role="alert">Publication comparison unavailable. <button type="button" className="underline" onClick={() => setReload(reload + 1)}>Retry comparison</button></p> : !base ? <p role="status">Loading registry comparison…</p> :
      <div className="flex min-h-0 flex-1">
        <nav aria-label="Publication changed files" className="w-48 shrink-0 overflow-auto border-r py-2">
          {paths.map((name) => <button type="button" key={name} aria-current={selected === name ? "true" : undefined}
            className="block w-full break-all px-2 py-1 text-left text-sm hover:bg-muted" onClick={() => setPath(name)}>{name}</button>)}
          {!paths.length && <p className="p-2 text-sm">No changes to publish.</p>}
        </nav>
        <div className="flex min-h-0 min-w-0 flex-1 flex-col"><p className="border-b px-2 py-1 text-sm">{selected}</p>
          {selected && <SkillFileDiff key={selected} path={selected} original={base.files.find((file) => file.path === selected)} current={snapshot.files.find((file) => file.path === selected)} />}
        </div>
      </div>}
    <div className="flex shrink-0 justify-between border-t pt-2">
      <button type="button" className="rounded border px-3 py-1" disabled={editor.busy || !!editor.pending} onClick={onClose}>Back to files</button>
      <button type="button" className="rounded border bg-primary px-3 py-1 text-primary-foreground disabled:opacity-50"
        disabled={!base || error || !paths.length || editor.busy || !!editor.pending || !editor.state?.can_publish || editor.status.startsWith("Published")}
        onClick={() => editor.publish(expectedLatest)}>Publish revision</button>
    </div>
    {showError && <ErrorPopup message="skill_manual_comparison_unavailable" context={{ nodeId: "skill-viewer", nodeLabel: "Skill publication" }} onDismiss={() => setShowError(false)} />}
  </section>;
}
