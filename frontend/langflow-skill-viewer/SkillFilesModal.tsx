import { dismissSkillActions } from "./SkillActions";
import SkillNavigation, { useSkillNavigation } from "./SkillNavigation";
import { useEffect, useRef, useState } from "react";
import SkillSearch, { type SkillMatch } from "./SkillSearch";
import * as monaco from "monaco-editor/editor";
import EditorWorker from "monaco-editor/editor/editor.worker?worker";
import "monaco-editor/languages/definitions/markdown/register";
import "monaco-editor/languages/definitions/python/register";
import "monaco-editor/languages/definitions/javascript/register";
import "monaco-editor/languages/features/json/register";
import JsonWorker from "monaco-editor/language/json/json.worker?worker";
import "monaco-editor/languages/definitions/shell/register";
import ReactMarkdown from "react-markdown";
import { api } from "@/controllers/API/api";
import { getBaseUrl } from "@/customization/utils/urls";
import { useDarkStore } from "@/stores/darkStore";
import BaseModal from "@/modals/baseModal";
import CommitTree, { RevisionDiff, type Commit, type SkillFile, type Snapshot } from "./SkillHistory";
import SkillSplitPane from "./SkillSplitPane";
import SkillExplorer from "./SkillExplorer";
import SkillOverview from "./SkillOverview";

// Bundle the editor and worker locally. No Monaco CDN or remote file loader.
(self as typeof self & { MonacoEnvironment?: object }).MonacoEnvironment = {
  getWorker: (_module: string, label: string) => label === "json" ? new JsonWorker() : new EditorWorker(),
};

function Source({ file, match }: { file: SkillFile; match: (SkillMatch & { selection: number }) | null }) {
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
    return () => { editor.current = null; instance.dispose(); model.dispose(); };
  }, [file, dark]);
  useEffect(() => {
    if (!match || match.path !== file.path || !editor.current) return;
    const range = new monaco.Range(match.line, match.column, match.line, match.column + match.length);
    editor.current.setSelection(range);
    editor.current.revealRangeInCenter(range);
    editor.current.focus();
  }, [file, dark, match]);
  return <div className="flex min-h-0 flex-1 flex-col">
    <div ref={container} className="min-h-0 flex-1" data-testid="skill-file-source" aria-label={`Read-only source: ${file.path}`} />
  </div>;
}

const ERROR_CODES = new Set(["invalid_skill_id", "immutable_skill_revision_required", "skill_revision_unavailable", "skill_revision_unsafe", "skill_revision_too_large"]);

export default function SkillFilesModal({ skillId, revision, open, setOpen }: {
  skillId: string; revision: string; open: boolean; setOpen: (value: boolean) => void;
}) {
  const content = useRef<HTMLDivElement>(null);
  const [fullPage, setFullPage] = useState(false);
  const [match, setMatch] = useState<(SkillMatch & { selection: number }) | null>(null);
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [reload, setReload] = useState(0);
  const [tabs, setTabs] = useState<string[]>([]);
  const [active, setActive] = useState("");
  const [preview, setPreview] = useState(false);
  const [historicalFiles, setHistoricalFiles] = useState<SkillFile[]>([]);
  const [selectedCommit, setSelectedCommit] = useState<Commit | null>(null);
  const navigationFiles = [...(snapshot?.files || []), ...historicalFiles.filter((old) => !snapshot?.files.some((current) => current.path === old.path))];
  const navigation = useSkillNavigation(`${skillId}:${revision}`, navigationFiles.map((file) => file.path));
  useEffect(() => {
    const controller = new AbortController();
    setSnapshot(null); setTabs([]); setActive(""); setError(""); setLoading(true); setPreview(false); setSelectedCommit(null); setHistoricalFiles([]); setMatch(null);
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
  const select = (path: string) => { setTabs((current) => current.includes(path) ? current : [...current, path]); setActive(path); setPreview(false); setMatch(null); };
  const close = (path: string) => {
    const next = tabs.filter((entry) => entry !== path); setTabs(next);
    if (active === path) { setActive(next[next.length - 1] || ""); setPreview(false); }
  };
  return <div className="contents" onKeyDownCapture={(event) => {
    // Keep canvas panning from consuming native button activation with Space.
    if (event.key === " " && event.target instanceof Element && event.target.closest("button")) event.stopPropagation();
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "f") {
      event.preventDefault(); event.stopPropagation(); navigation.showFind();
      content.current?.querySelector<HTMLButtonElement>('button[aria-label="Show skill navigation"]')?.click();
      requestAnimationFrame(() => content.current?.querySelector<HTMLInputElement>('input[aria-label="Search all Skill files"]')?.focus());
    }
  }}><BaseModal open={open} setOpen={setOpen} size="large"
    width={fullPage ? "100dvw" : "85dvw"} height={fullPage ? "100dvh" : undefined}
    className={fullPage ? "!max-h-[100dvh] !max-w-none !rounded-none" : "!min-w-0 !max-w-[100dvw]"}
    onEscapeKeyDown={(event) => {
      if (dismissSkillActions(event)) { event.preventDefault(); return; }
      if (navigation.open.Find && document.activeElement?.closest("#skill-Find-body")) {
        event.preventDefault(); navigation.hideFind(); content.current?.querySelector<HTMLButtonElement>("#skill-Find-toggle")?.focus();
      }
    }}>
    <BaseModal.Header description="Inspect the exact registered skill bundle. No files can be edited or executed.">
      <span>Skill files · Read only</span>
      <button type="button" aria-pressed={fullPage} className="ml-auto mr-6 rounded border px-2 py-1 text-sm font-normal hover:bg-muted"
        onClick={() => setFullPage(!fullPage)}>{fullPage ? "Restore window" : "Full page"}</button>
    </BaseModal.Header>
    <BaseModal.Content overflowHidden>
      <div ref={content} className="flex min-h-0 flex-1 flex-col">
      <div className="mb-2 text-sm" data-testid="skill-selection">{skillId}<br /><code title={revision}>{revision.startsWith("sha256:") ? `sha256:${revision.slice(7, 15)}…` : revision}</code></div>
      {loading && <p role="status">Loading selected skill revision…</p>}
      {error && <div role="alert"><p>Skill files unavailable: {error}</p>
        <button type="button" className="mt-2 rounded border px-3 py-1" onClick={() => setReload(reload + 1)}>Retry</button></div>}
      {snapshot && snapshot.skill_id === skillId && snapshot.revision_id === revision &&
        <SkillOverview key={`${skillId}:${revision}`} snapshot={snapshot} />}
      {snapshot && snapshot.skill_id === skillId && snapshot.revision_id === revision && <SkillSplitPane navigationActions={
        <button type="button" className="w-full px-2 py-1 text-left text-sm hover:bg-muted" onClick={navigation.toggleAll}>
          {navigation.allOpen ? "Collapse all" : "Open all"}
        </button>
      } navigation={<SkillNavigation open={navigation.open} onToggle={navigation.toggleSection}
        find={<SkillSearch key={`${skillId}:${revision}`} files={snapshot.files} onSelect={(result) => {
          setSelectedCommit(null); setHistoricalFiles([]); select(result.path);
          setMatch((previous) => ({ ...result, selection: (previous?.selection || 0) + 1 }));
        }} />}
        files={<>
        <nav aria-label="Skill file explorer" className="min-h-0 flex-1 overflow-auto pb-2">
          <div className="px-2 text-xs">{selectedCommit && <button type="button" className="float-right normal-case underline" onClick={() => { setSelectedCommit(null); setHistoricalFiles([]);
            const currentTabs = tabs.filter((path) => snapshot.files.some((file) => file.path === path));
            const next = snapshot.files.some((file) => file.path === active) ? active :
              currentTabs[0] || snapshot.files.find((file) => file.path === "SKILL.md")?.path || snapshot.files[0]?.path || "";
            setTabs(currentTabs.includes(next) || !next ? currentTabs : [...currentTabs, next]); setActive(next);
          }}>Current source</button>}</div>
          <SkillExplorer files={navigationFiles} select={select} active={active} collapsed={navigation.collapsedFolders} onToggle={navigation.toggleFolder} />
        </nav>
        </>} commits={<CommitTree key={`${skillId}:${revision}`} skillId={skillId} revision={revision}
          selected={selectedCommit?.commit_id || ""} onSelect={setSelectedCommit} />} />}>
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
              </div> : <Source file={file} match={match} />}
          </>}
          {!file && <p className="p-4">Select a file.</p>}
        </section>}
      </SkillSplitPane>}
      </div>
    </BaseModal.Content>
  </BaseModal></div>;
}
