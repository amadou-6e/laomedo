import { dismissSkillActions } from "./SkillActions";
import SkillNavigation, { useSkillNavigation } from "./SkillNavigation";
import { useCallback, useEffect, useRef, useState } from "react";
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
import SkillFileManager, { type SkillFileManagerHandle } from "./SkillFileManager";
import SkillOverview from "./SkillOverview";
import { VscChromeMaximize, VscChromeRestore, VscCode, VscLoading, VscPreview } from "react-icons/vsc";
import { useSkillEditing } from "./SkillEditing";
import { useRegistryComparison } from "./SkillPublication";
import SkillFileDiff from "./SkillFileDiff";
import ErrorPopup from "@/components/laomedoErrors/ErrorPopup";

// Bundle the editor and worker locally. No Monaco CDN or remote file loader.
(self as typeof self & { MonacoEnvironment?: object }).MonacoEnvironment = {
  getWorker: (_module: string, label: string) => label === "json" ? new JsonWorker() : new EditorWorker(),
};

function Source({ file, match, editable = false, onChange }: { file: SkillFile; match: (SkillMatch & { selection: number }) | null;
  editable?: boolean; onChange?: (path: string, text: string) => void }) {
  const container = useRef<HTMLDivElement>(null);
  const editor = useRef<monaco.editor.IStandaloneCodeEditor | null>(null);
  const dark = useDarkStore((state) => state.dark);
  const change = useRef(onChange); change.current = onChange;
  useEffect(() => {
    const extension = file.path.split(".").pop()?.toLowerCase();
    const language = ({ md: "markdown", py: "python", js: "javascript", mjs: "javascript", json: "json", sh: "shell" } as Record<string, string>)[extension || ""] || "plaintext";
    const model = monaco.editor.createModel(file.text || "", language);
    const instance = monaco.editor.create(container.current!, { model, readOnly: !editable, domReadOnly: !editable,
      // Langflow exempts textareas from canvas shortcuts. Chrome's experimental
      // EditContext uses a non-editable div, so ordinary letters trigger them.
      editContext: false,
      automaticLayout: true, minimap: { enabled: false }, scrollBeyondLastLine: false,
      theme: dark ? "vs-dark" : "vs", fontSize: 14, fontFamily: "'JetBrains Mono', monospace" });
    editor.current = instance;
    const listener = model.onDidChangeContent(() => { if (editable) change.current?.(file.path, model.getValue()); });
    return () => { editor.current = null; listener.dispose(); instance.dispose(); model.dispose(); };
  }, [file.path, file.file_hash, dark, editable]);
  useEffect(() => {
    if (!match || match.path !== file.path || !editor.current) return;
    const range = new monaco.Range(match.line, match.column, match.line, match.column + match.length);
    editor.current.setSelection(range);
    editor.current.revealRangeInCenter(range);
    editor.current.focus();
  }, [file.path, dark, match, editable]);
  return <div className="flex min-h-0 flex-1 flex-col">
    <div ref={container} className="min-h-0 flex-1" data-testid="skill-file-source" aria-label={`${editable ? "Editable" : "Read-only"} source: ${file.path}`} />
  </div>;
}

const ERROR_CODES = new Set(["invalid_skill_id", "immutable_skill_revision_required", "skill_revision_unavailable", "skill_revision_unsafe", "skill_revision_too_large"]);

export default function SkillFilesModal({ skillId, revision, open, setOpen }: {
  skillId: string; revision: string; open: boolean; setOpen: (value: boolean) => void;
}) {
  return open ? <SkillWorkspace key={`${skillId}:${revision}`} skillId={skillId} initialRevision={revision} setOpen={setOpen} /> : null;
}

function SkillWorkspace({ skillId, initialRevision, setOpen }: { skillId: string; initialRevision: string; setOpen: (value: boolean) => void }) {
  const open = true;
  const [revision, setRevision] = useState(initialRevision);
  const content = useRef<HTMLDivElement>(null);
  const [contentNode, setContentNode] = useState<HTMLDivElement | null>(null);
  const attachContent = useCallback((node: HTMLDivElement | null) => { content.current = node; if (node) setContentNode(node); }, []);
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
  const [discardAction, setDiscardAction] = useState<"close" | "discard" | null>(null);
  const [closeNotice, setCloseNotice] = useState(false);
  const [fileImporting, setFileImporting] = useState(false);
  const fileActions = useRef<SkillFileManagerHandle>(null);
  const manual = useSkillEditing(skillId, revision, snapshot, setRevision, fileImporting);
  const comparison = useRegistryComparison(skillId, manual.state?.latest_revision || "", manual.files);
  const [comparisonPath, setComparisonPath] = useState<string | null>(null);
  const navigationFiles = [...manual.files, ...historicalFiles.filter((old) => !manual.files.some((current) => current.path === old.path))];
  const navigation = useSkillNavigation(`${skillId}:${revision}`, navigationFiles.map((file) => file.path));
  useEffect(() => {
    if (selectedCommit || !snapshot || snapshot.revision_id !== revision) return;
    setTabs((current) => current.every((path) => manual.files.some((file) => file.path === path)) ? current : current.filter((path) => manual.files.some((file) => file.path === path)));
    setActive((current) => manual.files.some((file) => file.path === current) ? current : manual.files.find((file) => file.path === "SKILL.md")?.path || manual.files[0]?.path || "");
  }, [manual.files, selectedCommit, snapshot, revision]);
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
  const file = manual.files.find((entry) => entry.path === active);
  const markdown = file?.path.toLowerCase().endsWith(".md");
  const select = (path: string) => { setComparisonPath(null); setTabs((current) => current.includes(path) ? current : [...current, path]); setActive(path); setPreview(false); setMatch(null); };
  const close = (path: string) => {
    const next = tabs.filter((entry) => entry !== path); setTabs(next);
    if (active === path) { setActive(next[next.length - 1] || ""); setPreview(false); }
  };
  const requestClose = (value: boolean) => {
    if (value) return;
    if (manual.busy || manual.pending || fileImporting) { setCloseNotice(true); return; }
    if (manual.dirty) setDiscardAction("close"); else setOpen(false);
  };
  return <div className="contents" onKeyDownCapture={(event) => {
    // Keep canvas panning from consuming native button activation with Space.
    if (event.key === " " && event.target instanceof Element && event.target.closest("button")) event.stopPropagation();
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "f") {
      event.preventDefault(); event.stopPropagation(); setPreview(false); navigation.showFind();
      content.current?.querySelector<HTMLButtonElement>('button[aria-label="Show skill navigation"]')?.click();
      requestAnimationFrame(() => content.current?.querySelector<HTMLInputElement>('input[aria-label="Search all Skill files"]')?.focus());
    }
  }}><BaseModal open={open} setOpen={requestClose} size="large"
    width={fullPage ? "100dvw" : "85dvw"} height={fullPage ? "100dvh" : undefined}
    className={fullPage ? "!max-h-[100dvh] !max-w-none !rounded-none" : "!min-w-0 !max-w-[100dvw]"}
    onEscapeKeyDown={(event) => {
      // Radix handles Escape at document level before the card's React handler.
      // Consume the native event too: removing the card during document capture
      // must not send the same Escape to outer node/browser dismissal handlers.
      if (manual.error) { event.preventDefault(); event.stopImmediatePropagation(); manual.dismissError(); return; }
      if (comparison.showError && manual.dirty) { event.preventDefault(); event.stopImmediatePropagation(); comparison.dismissError(); return; }
      // Other presenters own their dismissal; let the card's handler receive
      // Escape after preventing Radix from dismissing the workspace.
      if (event.target instanceof Element && event.target.closest("[data-error-code]")) { event.preventDefault(); return; }
      if (fileActions.current?.dismiss()) { event.preventDefault(); event.stopImmediatePropagation(); return; }
      if (dismissSkillActions(event)) { event.preventDefault(); return; }
      if (navigation.open.Find && document.activeElement?.closest("#skill-Find-body")) {
        event.preventDefault(); navigation.hideFind(); content.current?.querySelector<HTMLButtonElement>("#skill-Find-toggle")?.focus();
      }
    }}>
    <BaseModal.Header>
      <span>Skill files{manual.state && !manual.state.edit_enabled ? " · Read only" : ""}</span>
      <button type="button" aria-label={fullPage ? "Restore window" : "Full page"} title={fullPage ? "Restore window" : "Full page"}
        aria-pressed={fullPage} className="ml-auto mr-6 inline-flex h-8 w-8 items-center justify-center rounded hover:bg-muted"
        onClick={() => setFullPage(!fullPage)}>{fullPage ? <VscChromeRestore aria-hidden="true" size={16} /> : <VscChromeMaximize aria-hidden="true" size={16} />}</button>
    </BaseModal.Header>
    <BaseModal.Content overflowHidden>
      <div ref={attachContent} className="flex min-h-0 flex-1 flex-col">
      <div className="mb-2 flex min-w-0 shrink-0 items-center gap-3 text-sm" data-testid="skill-selection">
        <span className="truncate" title={skillId}>{skillId}</span><code className="shrink-0 text-xs text-muted-foreground" title={revision}>{revision.startsWith("sha256:") ? `sha256:${revision.slice(7, 15)}` : revision}</code>
        {revision !== initialRevision && <span className="truncate text-xs text-muted-foreground" title={initialRevision}>Graph pins {initialRevision.slice(7, 15)}</span>}
      </div>
      {manual.controlsUnavailable && !manual.busy && <button type="button" className="mb-2 self-start rounded border px-3 py-1 text-sm" onClick={manual.refresh}>Retry edit controls</button>}
      {manual.state && !manual.state.edit_enabled && <p className="mb-2 text-xs text-muted-foreground">Manual editing is disabled for this Skill in local configuration.</p>}
      {closeNotice && (manual.busy || manual.pending) && <p role="status" className="mb-2 shrink-0 text-sm">Wait for confirmation, or use Check result before closing. Closing cannot cancel a save or publication.</p>}
      {fileImporting && <p role="status" className="mb-2 inline-flex shrink-0 items-center gap-1 text-sm"><VscLoading aria-hidden="true" className="animate-spin" />Importing local files...</p>}
      {manual.status && <p role="status" className="mb-2 shrink-0 text-sm">{manual.status}</p>}
      {discardAction && <div role="alertdialog" aria-label="Unsaved Skill changes" className="mb-2 shrink-0 rounded border p-2 text-sm">
        <p>Discard working changes and reload the latest saved files? Saved commits remain in history. Copy any text you want to keep first.</p><div className="mt-2 flex gap-2">
          <button type="button" className="rounded border px-3 py-1" onClick={() => setDiscardAction(null)}>Keep editing</button>
          <button type="button" className="rounded border px-3 py-1" onClick={() => { manual.discard(); if (discardAction === "close") setOpen(false);

            setDiscardAction(null); }}>Discard changes</button>
        </div>
      </div>}
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
        find={<SkillSearch key={`${skillId}:${revision}`} files={manual.files} collapsed={navigation.collapsedFolders} onToggle={navigation.toggleFolder} onSelect={(result) => {
          setSelectedCommit(null); setHistoricalFiles([]); select(result.path);
          setMatch((previous) => ({ ...result, selection: (previous?.selection || 0) + 1 }));
        }} />}
        files={<>
        <nav aria-label="Skill file explorer" className="min-h-0 flex-1 overflow-auto pb-2">
          <div className="px-2 text-xs">{selectedCommit && <button type="button" className="float-right normal-case underline" onClick={() => { setSelectedCommit(null); setHistoricalFiles([]);
            const currentTabs = tabs.filter((path) => manual.files.some((file) => file.path === path));
            const next = manual.files.some((file) => file.path === active) ? active :
              currentTabs[0] || manual.files.find((file) => file.path === "SKILL.md")?.path || manual.files[0]?.path || "";
            setTabs(currentTabs.includes(next) || !next ? currentTabs : [...currentTabs, next]); setActive(next);
          }}>Current source</button>}</div>
          <SkillFileManager ref={fileActions} manual={manual} files={navigationFiles} select={select} active={active}
            collapsed={navigation.collapsedFolders} onToggle={navigation.toggleFolder} portal={contentNode} onImporting={setFileImporting}
            disabledReason={selectedCommit ? "Historical comparison is read only." : fileImporting ? "Importing local files." : manual.busy ? "Publishing changes." : manual.pending ? "Check the pending result before changing files." : !manual.editing ? "File changes require local edit permission at the current head." : ""}
            onRemap={(source, destination) => {
              const map = (path: string) => path === source || path.startsWith(source + "/") ? destination + path.slice(source.length) : path;
              setTabs((current) => [...new Set(current.map(map))]); setActive((current) => map(current)); setComparisonPath(null); setPreview(false);
            }} />
        </nav>
        </>} commits={<CommitTree key={`${skillId}:${revision}`} skillId={skillId} revision={revision}
          selected={selectedCommit?.commit_id || ""} onSelect={(commit) => { setComparisonPath(null); setSelectedCommit(commit); }} />} />}>
        {comparisonPath !== null && comparison.base ? <section className="flex min-h-0 min-w-0 flex-1 flex-col" aria-label="Registry comparison">
          <div className="flex shrink-0 items-center gap-2 border-b px-2 py-1 text-sm"><span className="min-w-0 flex-1 truncate">{comparisonPath} · Registry current → working copy</span>
            <button type="button" className="shrink-0 rounded border px-2 py-1" onClick={() => setComparisonPath(null)}>Current source</button></div>
          <SkillFileDiff key={comparisonPath} path={comparisonPath} original={comparison.base.files.find((entry) => entry.path === comparisonPath)} current={manual.files.find((entry) => entry.path === comparisonPath)} />
        </section> : selectedCommit ? <RevisionDiff key={`${skillId}:${revision}:${selectedCommit.commit_id}`}
          skillId={skillId} revision={revision} commit={selectedCommit} path={active} current={file} onFiles={setHistoricalFiles} /> : <section aria-label="Selected skill file" className="flex min-h-0 min-w-0 flex-1 flex-col">
          <div className="flex shrink-0 items-center border-b">
            <div className="flex min-w-0 flex-1 overflow-x-auto" aria-label="Open files">
            {tabs.map((path) => <div className="flex shrink-0 items-center" key={path}>
              <button type="button" aria-pressed={path === active} className="px-3 py-2 text-sm hover:bg-muted" onClick={() => { setActive(path); setPreview(false); }}>{path}{manual.changes.some((change) => change.path === path) ? " •" : ""}</button>
              <button type="button" aria-label={`Close ${path}`} className="pr-3" onClick={() => close(path)}>×</button>
            </div>)}
            </div>
            {markdown && file?.kind === "text" && <button type="button" aria-pressed={preview}
              aria-label={preview ? "Show source" : "Preview Markdown"} title={preview ? "Show source" : "Preview Markdown"}
              className="m-1 flex h-8 w-8 shrink-0 items-center justify-center rounded hover:bg-muted focus-visible:outline focus-visible:outline-2 focus-visible:outline-ring"
              onClick={() => setPreview((current) => !current)}>
              {preview ? <VscCode aria-hidden="true" className="h-4 w-4" /> : <VscPreview aria-hidden="true" className="h-4 w-4" />}
            </button>}
          </div>
          {file && <>
            {file.kind === "binary" ? <p className="p-4">Preview unavailable for binary files.<br /><code>{file.file_hash}</code></p> :
              preview && markdown ? <div className="prose prose-sm max-w-none flex-1 overflow-auto p-4 dark:prose-invert" data-testid="skill-markdown-preview">
                <ReactMarkdown skipHtml components={{ a: ({ children }) => <span>{children}</span>, img: ({ alt }) => <span>[Image: {alt || "not loaded"}]</span> }}>{file.text || ""}</ReactMarkdown>
              </div> : <Source file={file} match={match} editable={manual.editing && !manual.busy && !manual.pending && !fileImporting} onChange={manual.update} />}
          </>}
          {!file && <p className="p-4">Select a file.</p>}
        </section>}
      </SkillSplitPane>}
      {manual.dirty && <div className="mt-2 flex shrink-0 flex-wrap items-center justify-end gap-2 border-t pt-2 text-sm" aria-label="Publish Skill changes">
        <div className="relative mr-auto min-w-0 text-xs">
          {comparison.base ? <details><summary className="cursor-pointer">{comparison.paths.length} {comparison.paths.length === 1 ? "file" : "files"} to publish{manual.state?.head_revision !== manual.state?.latest_revision ? " · Includes saved changes" : ""}</summary>
            <nav aria-label="Files to publish" className="absolute bottom-full left-0 z-10 mb-2 max-h-48 min-w-56 max-w-[70vw] overflow-auto rounded border bg-background p-1 shadow-md">
              {comparison.paths.map((path) => <button key={path} type="button" className="block w-full break-all px-2 py-1 text-left hover:bg-muted"
                onClick={(event) => { setComparisonPath(path); event.currentTarget.closest("details")?.removeAttribute("open"); }}>{path}</button>)}
            </nav></details> : comparison.failed ? <button type="button" className="underline" onClick={comparison.retry}>Retry comparison</button> : <span role="status">Loading publication changes…</span>}
          {manual.candidate && <span className="block text-muted-foreground">Saved commit awaiting publication</span>}
        </div>
        <input aria-label="Commit message" placeholder="Commit message (optional)" value={manual.message} maxLength={2000}
          disabled={manual.busy || !!manual.pending || fileImporting} className="min-w-0 max-w-64 rounded border bg-background px-2 py-1"
          onChange={(event) => manual.setMessage(event.target.value)} />
        {manual.busy && <span role="status" className="inline-flex items-center gap-1"><VscLoading className="animate-spin" aria-hidden="true" />Publishing…</span>}
        {!manual.busy && manual.pending && <button type="button" className="rounded border px-3 py-1" onClick={manual.reconcile}>Check result</button>}
        {manual.state && (!manual.state.can_edit || !manual.state.can_publish) && !manual.busy && !manual.pending && <button type="button" className="rounded border px-3 py-1" onClick={manual.refresh}>Retry edit controls</button>}
        <button type="button" className="rounded border px-3 py-1 disabled:opacity-50" disabled={manual.busy || !!manual.pending || fileImporting}
          onClick={() => setDiscardAction("discard")}>Discard</button>
        <button type="button" className="rounded border bg-primary px-3 py-1 text-primary-foreground disabled:opacity-50"
          disabled={!comparison.base || !comparison.paths.length || !manual.state?.can_edit || !manual.state?.can_publish || manual.busy || !!manual.pending || fileImporting} onClick={() => { setComparisonPath(null); manual.publish(); }}>Publish</button>
      </div>}
      </div>
      {manual.error && <ErrorPopup message={manual.error} context={{ nodeId: "skill-viewer", nodeLabel: "Skill workspace", operation: manual.pending?.action }} onDismiss={manual.dismissError} />}
      {comparison.showError && manual.dirty && <ErrorPopup message="skill_manual_comparison_unavailable" context={{ nodeId: "skill-viewer", nodeLabel: "Skill workspace" }} onDismiss={comparison.dismissError} />}
    </BaseModal.Content>
  </BaseModal></div>;
}
