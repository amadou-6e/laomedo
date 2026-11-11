import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import BaseModal from "@/modals/baseModal";
import ErrorExplanation from "@/components/laomedoErrors/ErrorExplanation";
import { describeNodeFailure } from "@/components/laomedoErrors/nodeErrors";
import { ConnectionFailure } from "@/components/laomedoGitHubConnections/api";
import type { Snapshot } from "../models";
import SkillBinaryPreview from "../editor/SkillBinaryPreview";
import SkillSplitPane from "../workspace/SkillSplitPane";
import { privateSkillRequest, subscribePrivateInvalidation } from "./api";
import type { PrivateOrigin, PrivateSelection } from "./models";

export default function PrivateSkillViewer({ selection, skillId, revision, setOpen }: {
  selection: PrivateSelection; skillId: string; revision: string; setOpen: (value: boolean) => void;
}) {
  const [snapshot, setSnapshot] = useState<Snapshot>();
  const [history, setHistory] = useState<PrivateOrigin[]>([]);
  const [selectedRevision, setSelectedRevision] = useState(revision);
  const [active, setActive] = useState("SKILL.md");
  const [preview, setPreview] = useState(false);
  const [patch, setPatch] = useState<string>();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [reload, setReload] = useState(0);
  const epoch = useRef(0);
  const request = useRef<AbortController | undefined>(undefined);
  const clear = (code: string) => {
    ++epoch.current; request.current?.abort(); setSnapshot(undefined); setHistory([]); setPatch(undefined); setBusy(false); setError(code);
  };
  useEffect(() => subscribePrivateInvalidation(() => clear("github_connection_changed")), []);
  useEffect(() => {
    const current = ++epoch.current;
    const controller = new AbortController(); request.current = controller;
    setSnapshot(undefined); setHistory([]); setPatch(undefined); setError(""); setBusy(true);
    if (!skillId || !selectedRevision || !Number.isSafeInteger(selection.repositoryId) || selection.repositoryId <= 0) {
      clear("github_repository_access_unconfirmed"); return () => controller.abort();
    }
    Promise.all([
      privateSkillRequest<Snapshot>("inspect", selection, { skill_id: skillId, revision_id: selectedRevision }, controller.signal),
      privateSkillRequest<{ origins: PrivateOrigin[] }>("history", selection, { skill_id: skillId }, controller.signal),
    ]).then(([files, retained]) => {
      if (epoch.current !== current || controller.signal.aborted) return;
      if (files.schema_version !== "laomedo.skill-inspection.v1" || files.skill_id !== skillId || files.revision_id !== selectedRevision || files.tree_hash !== selectedRevision)
        throw new ConnectionFailure("github_repository_access_unconfirmed");
      setSnapshot(files); setHistory(retained.origins); setActive(files.files.find((file) => file.path === "SKILL.md")?.path || files.files[0]?.path || "");
    }).catch((failure) => {
      if (epoch.current === current && !controller.signal.aborted) clear(failure instanceof ConnectionFailure ? failure.code : "github_connection_unavailable");
    }).finally(() => { if (epoch.current === current) setBusy(false); });
    return () => { controller.abort(); ++epoch.current; };
  }, [selection.connectionId, selection.repositoryId, skillId, selectedRevision, reload]);
  const compare = async () => {
    const current = ++epoch.current;
    setBusy(true); setPatch(undefined);
    try {
      const result = await privateSkillRequest<{ patch: string }>("compare", selection, { skill_id: skillId, before: revision, after: selectedRevision });
      if (epoch.current === current) setPatch(result.patch);
    } catch (failure) { if (epoch.current === current) clear(failure instanceof ConnectionFailure ? failure.code : "github_connection_unavailable"); }
    finally { if (epoch.current === current) setBusy(false); }
  };
  const file = snapshot?.files.find((entry) => entry.path === active);
  return <BaseModal open setOpen={setOpen} size="large" width="85dvw" className="!min-w-0 !max-w-[100dvw]">
    <BaseModal.Header><span>Skill files · Read only</span></BaseModal.Header>
    <BaseModal.Content overflowHidden>
      <div className="flex min-h-0 flex-1 flex-col gap-2" onKeyDown={(event) => event.stopPropagation()}>
        {busy && <p role="status">Verifying private access…</p>}
        {error && <div role="alert"><ErrorExplanation failure={describeNodeFailure(error, undefined)} />
          <p>Private content is hidden. Source and revision selections are preserved.</p></div>}
        <div className="flex gap-3 text-sm"><button type="button" className="rounded border px-3 py-1" disabled={busy} onClick={() => setReload((value) => value + 1)}>Refresh access</button>
          <a className="text-primary underline" href="/settings/github" target="_blank" rel="noreferrer">Manage GitHub connections</a></div>
        {snapshot && <SkillSplitPane navigation={<div className="flex min-h-0 flex-col overflow-auto text-sm">
          <h2 className="p-2 font-semibold">Files</h2>
          {snapshot.files.map((entry) => <button key={entry.path} type="button" aria-pressed={active === entry.path} className="truncate px-2 py-1 text-left hover:bg-muted" onClick={() => { setActive(entry.path); setPatch(undefined); setPreview(false); }}>{entry.path}</button>)}
          <h2 className="p-2 font-semibold">History</h2>
          {history.map((origin) => <button key={`${origin.label}:${origin.commit}:${origin.revision_id}`} type="button" className="break-all px-2 py-1 text-left hover:bg-muted" disabled={busy}
            onClick={() => setSelectedRevision(origin.revision_id)}>{origin.label} · {origin.commit.slice(0, 8)}</button>)}
        </div>} children={<div className="flex min-h-0 flex-1 flex-col overflow-auto">
          <div className="flex flex-wrap gap-2 border-b p-2 text-sm"><span className="break-all">{active}</span>
            {file?.kind === "text" && <button type="button" className="rounded border px-2" onClick={() => setPreview((value) => !value)}>{preview ? "Source" : "Preview"}</button>}
            {selectedRevision !== revision && <button type="button" disabled={busy} className="rounded border px-2" onClick={() => void compare()}>Compare with pinned revision</button>}</div>
          {patch !== undefined ? <pre className="overflow-auto whitespace-pre p-3 text-xs">{patch}</pre> : file?.kind === "binary" ? <SkillBinaryPreview key={`${selectedRevision}:${active}`} file={file} /> : preview && active.toLowerCase().endsWith(".md") ? <div className="prose max-w-none p-3 dark:prose-invert"><ReactMarkdown skipHtml components={{ img: () => null, a: ({ children }) => <span>{children}</span> }}>{file?.text || ""}</ReactMarkdown></div> : <pre className="overflow-auto whitespace-pre p-3 text-xs">{file?.text || ""}</pre>}
        </div>} />}
      </div>
    </BaseModal.Content>
  </BaseModal>;
}
