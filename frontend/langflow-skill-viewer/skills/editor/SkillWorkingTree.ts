import { sha256 } from "js-sha256";
import { fromByteArray } from "base64-js";
import type { SkillFile } from "../models";

export type WorkingFile = SkillFile & { contentBase64?: string; sourcePath?: string };
export type FileEdit = { path: string; content: string | null; encoding?: "base64" } | { path: string; source_path: string };
export type FileBuffers = Map<string, WorkingFile | null>;
export type WorkingTree = { files: WorkingFile[]; folders: string[] };
export type TreeChange = { before: WorkingTree; after: WorkingTree; move?: { source: string; destination: string } };
export const fileActionErrors = ["skill_manual_file_invalid", "skill_manual_file_conflict", "skill_manual_file_limit",
  "skill_manual_file_read_failed", "skill_manual_clipboard_unavailable"] as const;
const MAX_FILE = 512 * 1024, MAX_BUNDLE = 4 * 1024 * 1024;
const secret = /^(?:\.env.*|auth\.json|credentials(?:\.json)?|\.netrc|tokens?(?:\.json)?|id_rsa|id_ed25519)$|\.(?:pem|key)$/i;
const own = (path: string, parent: string) => path === parent || path.startsWith(parent + "/");
export const parentPath = (path: string) => path.split("/").slice(0, -1).join("/");
export const baseName = (path: string) => path.split("/").at(-1) || "";
export const joinPath = (folder: string, name: string) => folder ? `${folder}/${name}` : name;

export function folderPaths(files: SkillFile[], folders: string[] = []): string[] {
  return [...new Set([...folders, ...files.map((file) => parentPath(file.path))].flatMap((path) =>
    path.split("/").map((_, index, parts) => parts.slice(0, index + 1).join("/")).filter(Boolean)))].sort();
}

export function validateTree(base: SkillFile[], tree: WorkingTree) {
  validateWorkingOperation(base, tree.files);
  const folders = folderPaths(tree.files, tree.folders);
  if (folders.length > 256) throw Error("skill_manual_file_limit");
  for (const folder of folders) {
    const key = folder.toLowerCase();
    if (folders.some((other) => other !== folder && other.toLowerCase() === key) ||
      tree.files.some((file) => own(key, file.path.toLowerCase()))) throw Error("skill_manual_file_conflict");
  }
}

export function moveTree(tree: WorkingTree, source: string, destination: string): WorkingTree {
  validateFilePath(destination);
  const folders = folderPaths(tree.files, tree.folders), folder = folders.includes(source);
  if (!source || source === "SKILL.md" || own(destination, source) && source !== destination) throw Error("skill_manual_file_invalid");
  if (source === destination) return tree;
  if (folders.some((path) => !own(path, source) && path.toLowerCase() === destination.toLowerCase()) ||
    source.toLowerCase() === destination.toLowerCase()) throw Error("skill_manual_file_conflict");
  const files = tree.files.some((file) => own(file.path, source)) ? moveFiles(tree.files, source, destination) : tree.files;
  if (!folder && files === tree.files) throw Error("skill_manual_file_invalid");
  return { files, folders: folderPaths(files, folders.map((path) => folder && own(path, source) ? destination + path.slice(source.length) : path)) };
}

export function deleteTree(tree: WorkingTree, path: string): WorkingTree {
  const folders = folderPaths(tree.files, tree.folders);
  if (!path || path === "SKILL.md" || !folders.includes(path) && !tree.files.some((file) => own(file.path, path))) throw Error("skill_manual_file_invalid");
  return { files: tree.files.filter((file) => !own(file.path, path)), folders: folders.filter((folder) => !own(folder, path)) };
}

/** Apply only the action's path delta; unrelated editor changes remain intact. */
export function replayTreeChange(current: WorkingTree, change: TreeChange, undo: boolean): WorkingTree {
  const from = undo ? change.after : change.before, to = undo ? change.before : change.after;
  const before = new Map(from.files.map((file) => [file.path, file])), after = new Map(to.files.map((file) => [file.path, file]));
  const files = new Map(current.files.map((file) => [file.path, file]));
  const moved = new Map<string, WorkingFile>();
  if (change.move) {
    const source = undo ? change.move.destination : change.move.source, destination = undo ? change.move.source : change.move.destination;
    for (const file of current.files) if (own(file.path, source)) moved.set(destination + file.path.slice(source.length), file);
  }
  for (const path of new Set([...before.keys(), ...after.keys()])) {
    if (before.get(path) === after.get(path)) continue;
    const restored = after.get(path), edited = moved.get(path);
    if (!restored) files.delete(path);
    else files.set(path, edited ? { ...edited, path, sourcePath: restored.sourcePath } : restored);
  }
  const folders = new Set(current.folders);
  for (const path of from.folders) if (!to.folders.includes(path)) folders.delete(path);
  for (const path of to.folders) if (!from.folders.includes(path)) folders.add(path);
  return { files: [...files.values()], folders: folderPaths([...files.values()], [...folders]) };
}

export function validateFilePath(path: string) {
  const parts = path.split("/");
  if (!path || path.length > 512 || parts.length > 17 || /[\\:\x00-\x1f<>"|?*]/.test(path) || parts.some((part, index) =>
    !part || part === "." || part === ".." || /[. ]$/.test(part) || secret.test(part) ||
    /^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)/i.test(part) || index < parts.length - 1 && part.startsWith("."))) {
    throw Error("skill_manual_file_invalid");
  }
}

export function workingFiles(base: SkillFile[], buffers: FileBuffers): WorkingFile[] {
  const files = new Map<string, WorkingFile>(base.map((file) => [file.path, file]));
  for (const [path, value] of buffers) { if (value === null) files.delete(path); else files.set(path, value); }
  return [...files.values()].sort((a, b) => a.path < b.path ? -1 : a.path > b.path ? 1 : 0);
}

export function fileEdits(base: SkillFile[], files: WorkingFile[]): FileEdit[] {
  const before = new Map(base.map((file) => [file.path, file])), after = new Map(files.map((file) => [file.path, file]));
  return [...new Set([...before.keys(), ...after.keys()])].sort().flatMap((path): FileEdit[] => {
    const old = before.get(path), next = after.get(path);
    if (!next) return [{ path, content: null }];
    if (old && (old.kind === "text" && next.kind === "text" ? old.text === next.text : old.file_hash === next.file_hash)) return [];
    if (next.kind === "text") return [{ path, content: next.text! }];
    if (next.contentBase64 !== undefined) return [{ path, content: next.contentBase64, encoding: "base64" }];
    return [{ path, source_path: next.sourcePath || next.path }];
  });
}

export function validateWorkingOperation(base: SkillFile[], next: WorkingFile[]) {
  if (!next.some((file) => file.path === "SKILL.md")) throw Error("skill_manual_file_invalid");
  if (next.length > 128 || next.some((file) => file.bytes > MAX_FILE) || next.reduce((sum, file) => sum + file.bytes, 0) > MAX_BUNDLE) throw Error("skill_manual_file_limit");
  const seen: string[] = [];
  const edits = fileEdits(base, next);
  const originalPaths = new Set(base.map((file) => file.path));
  const destinations = new Set(edits.filter((edit) => !originalPaths.has(edit.path) && (!("content" in edit) || edit.content !== null)).map((edit) => edit.path));
  for (const file of next) {
    if (destinations.has(file.path)) validateFilePath(file.path);
    const path = file.path.toLowerCase();
    if (seen.some((old) => own(old, path) || own(path, old))) throw Error("skill_manual_file_conflict");
    seen.push(path);
  }
  // Python's host relay serializes JSON as ASCII. Reserve envelope/message/spacing
  // overhead, including surrogate escapes, before accepting an atomic file action.
  validateEditSize(edits);
}

export function validateEditSize(edits: FileEdit[]) {
  const encoded = JSON.stringify(edits).replace(/[^\x00-\x7f]/g, () => "\\u0000");
  if (edits.length > 128) throw Error("skill_manual_file_limit");
  if (encoded.length > MAX_BUNDLE - 32768) throw Error("skill_manual_file_limit");
}

export function moveFiles(files: WorkingFile[], source: string, destination: string): WorkingFile[] {
  validateFilePath(destination);
  if (!source || source === "SKILL.md" || own(destination, source) && source !== destination) throw Error("skill_manual_file_invalid");
  if (destination === source) return files;
  if (destination.toLowerCase() === source.toLowerCase()) throw Error("skill_manual_file_conflict");
  const moving = files.filter((file) => own(file.path, source)), remaining = files.filter((file) => !own(file.path, source));
  if (!moving.length) throw Error("skill_manual_file_invalid");
  if (remaining.some((file) => own(file.path.toLowerCase(), destination.toLowerCase()) || own(destination.toLowerCase(), file.path.toLowerCase()))) throw Error("skill_manual_file_conflict");
  return [...remaining, ...moving.map((file) => ({ ...file, path: destination + file.path.slice(source.length),
    sourcePath: file.kind === "binary" ? file.sourcePath || file.path : undefined }))];
}

export function deleteFiles(files: WorkingFile[], path: string): WorkingFile[] {
  if (!path || path === "SKILL.md" || !files.some((file) => own(file.path, path))) throw Error("skill_manual_file_invalid");
  return files.filter((file) => !own(file.path, path));
}

export async function readLocalFiles(files: File[], folder: string): Promise<WorkingFile[]> {
  if (!files.length || files.length > 128 || files.some((file) => file.size > MAX_FILE) || files.reduce((sum, file) => sum + file.size, 0) > MAX_BUNDLE) throw Error("skill_manual_file_limit");
  for (const file of files) { if (file.webkitRelativePath || file.name.includes("/")) throw Error("skill_manual_file_invalid"); validateFilePath(joinPath(folder, file.name)); }
  return Promise.all(files.map(async (file) => {
    let bytes: Uint8Array;
    try { bytes = new Uint8Array(await file.arrayBuffer()); } catch { throw Error("skill_manual_file_read_failed"); }
    if (bytes.length !== file.size || bytes.length > MAX_FILE) throw Error("skill_manual_file_read_failed");
    let text: string | null = null;
    try { if (!bytes.includes(0)) text = new TextDecoder("utf-8", { fatal: true, ignoreBOM: true }).decode(bytes); } catch { /* Binary bytes remain exact. */ }
    return { path: joinPath(folder, file.name), bytes: bytes.length, file_hash: "sha256:" + sha256(bytes),
      kind: text === null ? "binary" : "text", text, ...(text === null ? { contentBase64: fromByteArray(bytes) } : {}) };
  }));
}
