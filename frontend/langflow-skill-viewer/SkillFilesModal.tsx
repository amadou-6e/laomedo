import { useEffect, useRef, useState, type MutableRefObject } from "react";
import * as monaco from "monaco-editor/editor";
import EditorWorker from "monaco-editor/editor/editor.worker?worker";
import "monaco-editor/languages/definitions/markdown/register";
import "monaco-editor/languages/definitions/python/register";
import "monaco-editor/languages/definitions/javascript/register";
import "monaco-editor/languages/features/json/register";
import JsonWorker from "monaco-editor/language/json/json.worker?worker";
import "monaco-editor/languages/definitions/shell/register";
import "monaco-editor/features/find/register";
import ReactMarkdown from "react-markdown";
import { api } from "@/controllers/API/api";
import { getBaseUrl } from "@/customization/utils/urls";
import { useDarkStore } from "@/stores/darkStore";
import BaseModal from "@/modals/baseModal";
import CommitTree, { RevisionDiff, type Commit, type SkillFile, type Snapshot } from "./SkillHistory";
import SkillSplitPane from "./SkillSplitPane";
import SkillOverview from "./SkillOverview";

// Bundle the editor and worker locally. No Monaco CDN or remote file loader.
(self as typeof self & { MonacoEnvironment?: object }).MonacoEnvironment = {
  getWorker: (_module: string, label: string) => label === "json" ? new JsonWorker() : new EditorWorker(),
};

type Branch = { name: string; path: string; children?: Branch[] };

function tree(files: SkillFile[]): Branch[] {
  const roots: Branch[] = [];
  for (const file of files) {
    let level = roots;
    const parts = file.path.split("/");
    parts.forEach((name, index) => {
      let item = level.find((entry) => entry.name === name);
      if (!item) {
        item = { name, path: parts.slice(0, index + 1).join("/") };
        if (index < parts.length - 1) item.children = [];
        level.push(item);
      }
      if (item.children) level = item.children;
    });
  }
  return roots;
}

function Folder({ item, select, active }: { item: Branch; select: (path: string) => void; active: string }) {
  const [expanded, setExpanded] = useState(true);
  return <li>
    <button type="button" className="w-full rounded px-2 py-1 text-left text-sm hover:bg-muted"
      aria-expanded={item.children ? expanded : undefined}
      aria-current={!item.children && active === item.path ? "true" : undefined}
      onClick={() => item.children ? setExpanded(!expanded) : select(item.path)}>
      {item.children ? (expanded ? "▾ " : "▸ ") : ""}{item.name}
    </button>
    {item.children && expanded && <ul className="ml-3 border-l pl-1">
      {item.children.map((child) => <Folder key={child.path} item={child} select={select} active={active} />)}
    </ul>}
  </li>;
}

function Source({ file, closeFind }: { file: SkillFile; closeFind: MutableRefObject<(() => boolean) | null> }) {
  const container = useRef<HTMLDivElement>(null);
  const editor = useRef<monaco.editor.IStandaloneCodeEditor | null>(null);
  const dark = useDarkStore((state) => state.dark);
  useEffect(() => {
    const extension = file.path.split(".").pop()?.toLowerCase();
    const language = ({ md: "markdown", py: "python", js: "javascript", mjs: "javascript", json: "json", sh: "shell" } as Record<string, string>)[extension || ""] || "plaintext";
    const model = monaco.editor.createModel(file.text || "", language);
    const instance = monaco.editor.create(container.current!, { model, readOnly: true, domReadOnly: true,
      automaticLayout: true, minimap: { enabled: false }, scrollBeyondLastLine: false,
      theme: dark ? "vs-dark" : "vs", fontSize: 14, fontFamily: "'JetBrains Mono', monospace" });
    editor.current = instance;
    closeFind.current = () => {
      if (!container.current?.querySelector(".find-widget.visible")) return false;
      instance.trigger("skill-files", "closeFindWidget", null);
      return true;
    };
    return () => { closeFind.current = null; editor.current = null; instance.dispose(); model.dispose(); };
  }, [file, dark]);
  return <div className="flex min-h-0 flex-1 flex-col">
    <button type="button" className="self-end rounded px-3 py-1 text-sm hover:bg-muted"
      onClick={() => { editor.current?.focus(); void editor.current?.getAction("actions.find")?.run(); }}>Find in file</button>
    <div ref={container} className="min-h-0 flex-1" data-testid="skill-file-source" aria-label={`Read-only source: ${file.path}`} />
  </div>;
}

const ERROR_CODES = new Set(["invalid_skill_id", "immutable_skill_revision_required", "skill_revision_unavailable", "skill_revision_unsafe", "skill_revision_too_large"]);

export default function SkillFilesModal({ skillId, revision, open, setOpen }: {
  skillId: string; revision: string; open: boolean; setOpen: (value: boolean) => void;
}) {
  const closeFind = useRef<(() => boolean) | null>(null);
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [reload, setReload] = useState(0);
  const [tabs, setTabs] = useState<string[]>([]);
  const [active, setActive] = useState("");
  const [preview, setPreview] = useState(false);
  const [historicalFiles, setHistoricalFiles] = useState<SkillFile[]>([]);
  const [selectedCommit, setSelectedCommit] = useState<Commit | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    setSnapshot(null); setTabs([]); setActive(""); setError(""); setLoading(true); setPreview(false); setSelectedCommit(null); setHistoricalFiles([]);
    if (!open) { setLoading(false); return () => controller.abort(); }
    if (!skillId || !revision) {
      setError("Select a skill and revision first."); setLoading(false);
      return () => controller.abort();
    }
    const url = `${getBaseUrl()}laomedo/skills/${encodeURIComponent(skillId)}/${encodeURIComponent(revision)}`;
    api.get<Snapshot>(url, { signal: controller.signal }).then(({ data }) => {
      if (controller.signal.aborted) return;
      if (data.schema_version !== "laomedo.skill-inspection.v1" || data.skill_id !== skillId || data.revision_id !== revision || data.tree_hash !== revision) throw new Error("snapshot_identity_mismatch");
      setSnapshot(data);
      const first = data.files.find((file) => file.path === "SKILL.md")?.path || data.files[0]?.path || "";
      setTabs(first ? [first] : []); setActive(first);
    }).catch((failure) => {
      if (controller.signal.aborted) return;
      const code = failure.response?.data?.detail?.code;
      setError(ERROR_CODES.has(code) ? code : "skill_inspection_unavailable");
    }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [open, skillId, revision, reload]);
  const file = snapshot?.files.find((entry) => entry.path === active);
  const markdown = file?.path.toLowerCase().endsWith(".md");
  const select = (path: string) => { setTabs((current) => current.includes(path) ? current : [...current, path]); setActive(path); setPreview(false); };
  const close = (path: string) => {
    const next = tabs.filter((entry) => entry !== path); setTabs(next);
    if (active === path) { setActive(next[next.length - 1] || ""); setPreview(false); }
  };
  return <BaseModal open={open} setOpen={setOpen} size="large" onEscapeKeyDown={(event) => { if (closeFind.current?.()) event.preventDefault(); }}>
    <BaseModal.Header description="Inspect the exact registered skill bundle. No files can be edited or executed.">
      <span>Skill files · Read only</span>
    </BaseModal.Header>
    <BaseModal.Content overflowHidden>
      <div className="mb-2 text-sm" data-testid="skill-selection">{skillId}<br /><code title={revision}>{revision.startsWith("sha256:") ? `sha256:${revision.slice(7, 15)}…` : revision}</code></div>
      {loading && <p role="status">Loading selected skill revision…</p>}
      {error && <div role="alert"><p>Skill files unavailable: {error}</p>
        <button type="button" className="mt-2 rounded border px-3 py-1" onClick={() => setReload(reload + 1)}>Retry</button></div>}
      {snapshot && snapshot.skill_id === skillId && snapshot.revision_id === revision &&
        <SkillOverview key={`${skillId}:${revision}`} snapshot={snapshot} />}
      {snapshot && snapshot.skill_id === skillId && snapshot.revision_id === revision && <SkillSplitPane navigation={<>
        <nav aria-label="Skill file explorer" className="max-h-[45%] min-h-[100px] shrink-0 overflow-auto pb-3">
          <h3 className="mb-2 px-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Files {selectedCommit && <button type="button" className="float-right normal-case underline" onClick={() => { setSelectedCommit(null); setHistoricalFiles([]);
            const currentTabs = tabs.filter((path) => snapshot.files.some((file) => file.path === path));
            const next = snapshot.files.some((file) => file.path === active) ? active :
              currentTabs[0] || snapshot.files.find((file) => file.path === "SKILL.md")?.path || snapshot.files[0]?.path || "";
            setTabs(currentTabs.includes(next) || !next ? currentTabs : [...currentTabs, next]); setActive(next);
          }}>Current source</button>}</h3>
          <ul>{tree([...snapshot.files, ...historicalFiles.filter((old) => !snapshot.files.some((current) => current.path === old.path))]).map((item) => <Folder key={item.path} item={item} select={select} active={active} />)}</ul>
        </nav>
        <CommitTree key={`${skillId}:${revision}`} skillId={skillId} revision={revision}
          selected={selectedCommit?.commit_id || ""} onSelect={setSelectedCommit} />
      </>}>
        {selectedCommit ? <RevisionDiff key={`${skillId}:${revision}:${selectedCommit.commit_id}`}
          skillId={skillId} revision={revision} commit={selectedCommit} path={active} current={file} onFiles={setHistoricalFiles} /> : <section aria-label="Selected skill file" className="flex min-h-0 min-w-0 flex-1 flex-col">
          <div className="flex overflow-x-auto border-b" aria-label="Open files">
            {tabs.map((path) => <div className="flex shrink-0 items-center" key={path}>
              <button type="button" aria-pressed={path === active} className="px-3 py-2 text-sm hover:bg-muted" onClick={() => { setActive(path); setPreview(false); }}>{path}</button>
              <button type="button" aria-label={`Close ${path}`} className="pr-3" onClick={() => close(path)}>×</button>
            </div>)}
          </div>
          {file && <>
            <div className="flex items-center gap-2 border-b py-1">
              <button type="button" aria-pressed={!preview} className="rounded px-3 py-1 hover:bg-muted" onClick={() => setPreview(false)}>Source</button>
              {markdown && <button type="button" aria-pressed={preview} className="rounded px-3 py-1 hover:bg-muted" onClick={() => setPreview(true)}>Preview</button>}
              <span className="ml-auto text-xs">{file.bytes} bytes</span>
            </div>
            {file.kind === "binary" ? <p className="p-4">Preview unavailable for binary files.<br /><code>{file.file_hash}</code></p> :
              preview && markdown ? <div className="prose prose-sm max-w-none flex-1 overflow-auto p-4 dark:prose-invert" data-testid="skill-markdown-preview">
                <ReactMarkdown skipHtml components={{ a: ({ children }) => <span>{children}</span>, img: ({ alt }) => <span>[Image: {alt || "not loaded"}]</span> }}>{file.text || ""}</ReactMarkdown>
              </div> : <Source file={file} closeFind={closeFind} />}
          </>}
          {!file && <p className="p-4">Select a file.</p>}
        </section>}
      </SkillSplitPane>}
    </BaseModal.Content>
  </BaseModal>;
}
