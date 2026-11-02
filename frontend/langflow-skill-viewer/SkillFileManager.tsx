import * as Menu from "@radix-ui/react-dropdown-menu";
import { forwardRef, useEffect, useImperativeHandle, useRef, useState, type DragEvent, type ReactElement, type ReactNode } from "react";
import { VscCloudUpload, VscCopy, VscEdit, VscFolderOpened, VscTrash } from "react-icons/vsc";
import SkillExplorer, { type ExplorerEntry } from "./SkillExplorer";
import type { SkillEditing } from "./SkillEditing";
import { baseName, deleteFiles, fileActionErrors, joinPath, moveFiles, parentPath, readLocalFiles, validateFilePath } from "./SkillWorkingTree";

type Form = { kind: "rename" | "move" | "delete" | "copy"; path: string; folder: boolean };
export type SkillFileManagerHandle = { dismiss: () => boolean };
type Props = { manual: SkillEditing; files: SkillEditing["files"]; active: string; collapsed: Set<string>;
  select: (path: string) => void; onToggle: (path: string) => void; portal: HTMLElement | null;
  disabledReason: string; onImporting: (busy: boolean) => void; onRemap: (source: string, destination: string) => void };
const MIME = "application/x-laomedo-skill-path";
const itemClass = "flex cursor-default select-none items-center gap-2 rounded px-2 py-1.5 text-sm outline-none data-[highlighted]:bg-muted data-[disabled]:pointer-events-none data-[disabled]:opacity-50";

/** Explorer-local transient UI; durable working state belongs to SkillEditing. */
const SkillFileManager = forwardRef<SkillFileManagerHandle, Props>(function SkillFileManager(props, ref) {
  const { manual, files, disabledReason, onImporting } = props;
  const root = useRef<HTMLDivElement>(null), picker = useRef<HTMLInputElement>(null);
  const live = useRef(true), reading = useRef(false), uploadFolder = useRef("");
  const latestManual = useRef(manual); latestManual.current = manual;
  const dragged = useRef<string | null>(null), formRef = useRef<Form | null>(null);
  const [menu, setMenu] = useState<string | null>(null), [form, setForm] = useState<Form | null>(null);
  const [value, setValue] = useState(""), [dropFolder, setDropFolder] = useState<string | null>(null);
  useEffect(() => { live.current = true; return () => { live.current = false; }; }, []);
  const showForm = (next: Form | null) => { formRef.current = next; setForm(next); };
  const focus = (path: string) => requestAnimationFrame(() => {
    const input = root.current?.querySelector<HTMLInputElement | HTMLSelectElement>("[data-file-form]");
    if (input) { input.focus(); if (input instanceof HTMLInputElement) input.select(); return; }
    const target = [...(root.current?.querySelectorAll<HTMLElement>("[data-skill-file-path]") || [])].find((element) => element.dataset.skillFilePath === path);
    ((target?.firstElementChild as HTMLElement | null) || root.current)?.focus();
  });
  const cancel = () => { const path = formRef.current?.path || ""; showForm(null); focus(path); };
  useImperativeHandle(ref, () => ({ dismiss: () => {
    if (menu !== null) { const path = menu; setMenu(null); focus(path); return true; }
    if (formRef.current) { cancel(); return true; }
    return false;
  } }));
  useEffect(() => { if (form) focus(form.path); }, [form]);
  const fail = (failure: unknown) => {
    const code = failure instanceof Error && (fileActionErrors as readonly string[]).includes(failure.message) ? failure.message : "skill_manual_file_read_failed";
    manual.reportError(code);
  };
  const folders = [...new Set(files.flatMap((file) => file.path.split("/").slice(0, -1).map((_, index, parts) => parts.slice(0, index + 1).join("/"))))].sort();
  const commitMove = (path: string, destination: string) => {
    try {
      const next = moveFiles(manual.files, path, destination);
      if (manual.replaceFiles(next)) { props.onRemap(path, destination); showForm(null); focus(destination); }
    } catch (failure) { fail(failure); }
  };
  const applyForm = () => {
    if (!form || disabledReason || reading.current) return;
    if (form.kind === "rename") {
      try { if (value.includes("/")) throw Error("skill_manual_file_invalid"); validateFilePath(value); }
      catch (failure) { fail(failure); return; }
      commitMove(form.path, joinPath(parentPath(form.path), value));
    } else if (form.kind === "move") commitMove(form.path, joinPath(value, baseName(form.path)));
    else if (form.kind === "delete") {
      try { if (manual.replaceFiles(deleteFiles(manual.files, form.path))) { showForm(null); focus(""); } }
      catch (failure) { fail(failure); }
    }
  };
  const importFiles = async (selected: File[], folder: string) => {
    if (disabledReason || reading.current || !selected.length) return;
    reading.current = true; onImporting(true);
    try {
      const admitted = manual.state;
      if (folder && !manual.files.some((file) => file.path.startsWith(folder + "/"))) throw Error("skill_manual_file_invalid");
      const imported = await readLocalFiles(selected, folder);
      if (!live.current) return;
      const current = latestManual.current;
      if (!current.state) { current.reportError("skill_manual_controls_unavailable"); return; }
      if (current.state.head_commit !== admitted?.head_commit || current.state.selected_revision !== admitted?.selected_revision) {
        current.reportError("skill_manual_stale"); return;
      }
      if (current.pending || current.busy) return;
      if (!current.editing) {
        current.reportError("skill_manual_not_authorized"); return;
      }
      if (current.replaceFiles([...current.files, ...imported])) { showForm(null); props.select(imported[0].path); focus(imported[0].path); }
    } catch (failure) { if (live.current) fail(failure); }
    finally { reading.current = false; if (live.current) onImporting(false); }
  };
  const copy = async (entry: ExplorerEntry) => {
    try { await navigator.clipboard.writeText(entry.path || "."); }
    catch { showForm({ ...entry, kind: "copy" }); setValue(entry.path || "."); manual.reportError("skill_manual_clipboard_unavailable"); }
  };
  const dropTarget = (entry: ExplorerEntry) => entry.folder ? entry.path : parentPath(entry.path);
  const drop = (event: DragEvent, entry: ExplorerEntry) => {
    event.preventDefault(); event.stopPropagation(); setDropFolder(null);
    if (disabledReason || reading.current) return;
    const folder = dropTarget(entry), source = dragged.current;
    if (source !== null && event.dataTransfer.getData(MIME) === source) {
      dragged.current = null; commitMove(source, joinPath(folder, baseName(source))); return;
    }
    const items = [...event.dataTransfer.items];
    if (items.some((item) => item.kind === "file" && item.webkitGetAsEntry?.()?.isDirectory)) { fail(Error("skill_manual_file_invalid")); return; }
    void importFiles([...event.dataTransfer.files], folder);
  };
  const formView = (entry: ExplorerEntry): ReactNode => form?.path !== entry.path ? null : <form
    aria-label={`${form.kind === "copy" ? "Copy relative path" : form.kind === "delete" ? "Delete" : form.kind === "move" ? "Move" : "Rename"} ${entry.path || "root"}`}
    className="my-1 min-w-0 rounded border bg-background p-2 text-sm" onSubmit={(event) => { event.preventDefault(); applyForm(); }}>
    {form.kind === "delete" ? <p className="break-all">Delete {form.path}? {files.filter((file) => file.path === form.path || file.path.startsWith(form.path + "/")).length} file(s) will be removed from the working copy.</p> :
      <label className="block">{form.kind === "move" ? "Destination folder" : form.kind === "copy" ? "Relative path" : "Name"}
        {form.kind === "move" ? <select data-file-form className="mt-1 w-full min-w-0 rounded border bg-background p-1" value={value} disabled={!!disabledReason} onChange={(event) => setValue(event.target.value)}>
          {["", ...folders].filter((folder) => !entry.folder || folder !== entry.path && !folder.startsWith(entry.path + "/")).map((folder) => <option key={folder} value={folder}>{folder || "/ (Skill root)"}</option>)}
        </select> : <input data-file-form className="mt-1 w-full min-w-0 rounded border bg-background p-1" value={value} readOnly={form.kind === "copy"} disabled={form.kind !== "copy" && !!disabledReason} onChange={(event) => setValue(event.target.value)} />}
      </label>}
    <div className="mt-2 flex gap-2">{form.kind !== "copy" && <button type="submit" disabled={!!disabledReason} className="rounded border px-2 py-1 disabled:opacity-50">{form.kind === "delete" ? "Delete" : form.kind === "move" ? "Move" : "Rename"}</button>}
      <button type="button" className="rounded border px-2 py-1" onClick={cancel}>{form.kind === "copy" ? "Close path" : "Cancel"}</button></div>
  </form>;
  const decorate = (entry: ExplorerEntry, row: ReactElement) => <Menu.Root key={entry.path} open={menu === entry.path} onOpenChange={(open) => { setMenu(open ? entry.path : null); }}>
    <div className={`relative ${!entry.path ? "flex min-h-0 flex-1 flex-col" : ""} ${dropFolder === entry.path && entry.folder ? "bg-accent ring-1 ring-primary" : ""}`} data-skill-file-path={entry.path} draggable={!disabledReason && !!entry.path && entry.path !== "SKILL.md"}
      data-drop-target={dropFolder === entry.path && entry.folder ? "true" : undefined}
      onContextMenu={(event) => { event.preventDefault(); event.stopPropagation(); setMenu(entry.path); }}
      onKeyDown={(event) => {
        if (event.key !== "ContextMenu" && !(event.shiftKey && event.key === "F10")) return;
        event.preventDefault(); event.stopPropagation(); setMenu(entry.path);
      }}
      onDragStart={(event) => { if (disabledReason || !entry.path || entry.path === "SKILL.md") { event.preventDefault(); return; }
        dragged.current = entry.path; event.dataTransfer.setData(MIME, entry.path); event.dataTransfer.effectAllowed = "move"; event.stopPropagation(); }}
      onDragEnd={() => { dragged.current = null; setDropFolder(null); }}
      onDragOver={(event) => {
        if (disabledReason || !event.dataTransfer.types.some((type) => type === "Files" || type === MIME && dragged.current !== null)) return;
        event.preventDefault(); event.stopPropagation(); event.dataTransfer.dropEffect = dragged.current !== null ? "move" : "copy"; setDropFolder(dropTarget(entry));
      }} onDrop={(event) => drop(event, entry)}>{row}
      <Menu.Trigger asChild><button type="button" tabIndex={-1} aria-hidden="true" className="pointer-events-none absolute left-0 top-full h-px w-px opacity-0" /></Menu.Trigger>
    </div>
    {props.portal && <Menu.Portal container={props.portal}><Menu.Content data-skill-file-menu aria-labelledby={undefined} aria-label={`File actions: ${entry.path || "root"}`}
      side="bottom" align="start" collisionBoundary={props.portal} collisionPadding={8} className="z-50 min-w-48 max-w-[90vw] rounded border bg-background p-1 text-foreground shadow-md"
      // Windows emits contextmenu on key-up after the Menu key has opened and
      // focused this portal. Keep that event from reopening the explorer root.
      onContextMenu={(event) => { event.preventDefault(); event.stopPropagation(); }}
      onCloseAutoFocus={(event) => { event.preventDefault(); focus(entry.path); }}
      onEscapeKeyDown={(event) => { event.preventDefault(); setMenu(null); focus(entry.path); }}>
      {disabledReason && <Menu.Label className="max-w-64 px-2 py-1 text-xs text-muted-foreground">{disabledReason}</Menu.Label>}
      <Menu.Item className={itemClass} disabled={!!disabledReason} onSelect={() => { uploadFolder.current = dropTarget(entry); picker.current?.click(); }}><VscCloudUpload aria-hidden="true" />Upload files...</Menu.Item>
      {entry.path && <>
        <Menu.Item className={itemClass} disabled={!!disabledReason || entry.path === "SKILL.md"} onSelect={() => { setValue(baseName(entry.path)); showForm({ ...entry, kind: "rename" }); }}><VscEdit aria-hidden="true" />Rename...</Menu.Item>
        <Menu.Item className={itemClass} disabled={!!disabledReason || entry.path === "SKILL.md"} onSelect={() => { setValue(parentPath(entry.path)); showForm({ ...entry, kind: "move" }); }}><VscFolderOpened aria-hidden="true" />Move to...</Menu.Item>
        <Menu.Item className={itemClass} disabled={!!disabledReason || entry.path === "SKILL.md"} onSelect={() => showForm({ ...entry, kind: "delete" })}><VscTrash aria-hidden="true" />Delete...</Menu.Item>
        {entry.path === "SKILL.md" && <Menu.Label className="px-2 py-1 text-xs text-muted-foreground">Required Skill entrypoint</Menu.Label>}
      </>}
      <Menu.Item className={itemClass} onSelect={() => { void copy(entry); }}><VscCopy aria-hidden="true" />Copy relative path</Menu.Item>
    </Menu.Content></Menu.Portal>}
    {formView(entry)}
  </Menu.Root>;
  return <div ref={root} className="flex min-h-24 flex-1 flex-col" tabIndex={-1} aria-label="Skill files area">
    <input ref={picker} type="file" multiple hidden aria-label="Upload Skill files" onChange={(event) => { const selected = [...(event.target.files || [])]; event.target.value = ""; void importFiles(selected, uploadFolder.current); }} />
    {decorate({ path: "", folder: true }, <div tabIndex={0} role="group" aria-label="Skill file actions" className={`min-h-24 flex-1 outline-none focus-visible:ring-1 focus-visible:ring-primary ${dropFolder === "" ? "bg-accent ring-1 ring-primary" : ""}`}>
      <SkillExplorer files={files} active={props.active} collapsed={props.collapsed} select={props.select} onToggle={props.onToggle} decorate={decorate} />
    </div>)}
  </div>;
});
export default SkillFileManager;
