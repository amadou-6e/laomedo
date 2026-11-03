import { TextDecoder, TextEncoder } from "util";
import { createHash } from "crypto";
import { readFileSync } from "fs";
import { join } from "path";
import catalog from "@/components/laomedoErrors/node-error-catalog.json";
import { deleteFiles, deleteTree, fileEdits, folderPaths, moveFiles, moveTree, replayTreeChange, readLocalFiles, validateTree, validateWorkingOperation, type WorkingFile } from "./SkillWorkingTree";
Object.assign(global, { TextDecoder, TextEncoder });
const file = (path: string, text = "original"): WorkingFile => ({ path, text, kind: "text", bytes: Buffer.byteLength(text), file_hash: "sha256:" + createHash("sha256").update(text).digest("hex") });
const base = [file("SKILL.md"), file("refs/one.md")];
test("moving a last child retains its empty parent; folder actions and delta undo preserve dirty text", () => {
  const before = { files: base, folders: folderPaths(base) };
  const moved = moveTree(before, 'refs/one.md', 'one.md');
  expect(moved.folders).toContain('refs');
  const edited = { ...moved, files: moved.files.map((f) => f.path === 'SKILL.md' ? file(f.path, 'dirty editor text') : f.path === 'one.md' ? file(f.path, 'edited moved file') : f) };
  const undone = replayTreeChange(edited, { before, after: moved, move: { source: 'refs/one.md', destination: 'one.md' } }, true);
  expect(undone.files.find((f) => f.path === 'refs/one.md')?.text).toBe('edited moved file');
  expect(undone.files.find((f) => f.path === 'SKILL.md')?.text).toBe('dirty editor text');
  const renamed = moveTree(moved, 'refs', 'empty');
  expect(renamed.folders).toContain('empty'); expect(renamed.folders).not.toContain('refs');
  const deleted = deleteTree(edited, 'one.md');
  const restored = replayTreeChange(deleted, { before: edited, after: deleted }, true);
  expect(restored.files.find((f) => f.path === 'one.md')?.text).toBe('edited moved file');
  expect(() => validateTree(base, { ...moved, files: [...moved.files, file('refs')] })).toThrow('skill_manual_file_conflict');
  expect(() => moveTree(moved, 'refs', 'one.md/child')).not.toThrow();
  expect(() => validateTree(base, moveTree(moved, 'refs', 'one.md/child'))).toThrow('skill_manual_file_conflict');
});
function local(name: string, bytes: Uint8Array) {
  const value = new File([bytes], name);
  Object.defineProperty(value, "arrayBuffer", { value: async () => bytes.slice().buffer });
  return value;
}

test("multi-file uploads preserve binary bytes and text BOM, with hashes independent of WebCrypto", async () => {
  const png = new Uint8Array([137,80,78,71,13,10,26,10,0,255]), text = new TextEncoder().encode("\ufeffhello\r\n");
  const result = await readLocalFiles([local("image.png", png), local("note.md", text)], "refs");
  expect(result[0].file_hash).toBe("sha256:" + createHash("sha256").update(png).digest("hex"));
  expect(Buffer.from(result[0].contentBase64!, "base64")).toEqual(Buffer.from(png));
  expect(result[1].text).toBe("\ufeffhello\r\n");
  expect(fileEdits(base, [...base, ...result])).toEqual([{ path: "refs/image.png", content: Buffer.from(png).toString("base64"), encoding: "base64" }, { path: "refs/note.md", content: "\ufeffhello\r\n" }]);
});

test("moves retain unsaved text and immutable binary origins across repeated moves", () => {
  const binary: WorkingFile = { path: "refs/icon.png", text: null, kind: "binary", bytes: 10, file_hash: "exact-base-hash" };
  const starting = [base[0], file("refs/one.md", "unsaved"), binary];
  const first = moveFiles(starting, "refs", "renamed"), second = moveFiles(first, "renamed", "final");
  validateWorkingOperation([...base, binary], second);
  expect(fileEdits([...base, binary], second)).toEqual([
    { path: "final/icon.png", source_path: "refs/icon.png" }, { path: "final/one.md", content: "unsaved" },
    { path: "refs/icon.png", content: null }, { path: "refs/one.md", content: null },
  ]);
  expect(starting[1].path).toBe("refs/one.md");
  expect(deleteFiles(second, "final")).toEqual([base[0]]);
});

test("new-path safety restrictions leave unchanged legacy paths usable during unrelated file actions", () => {
  const existing = [...base, file(".github/instructions.md"), file("token.json")];
  const renamed = moveFiles(existing, "refs/one.md", "refs/renamed.md");
  expect(() => validateWorkingOperation(existing, renamed)).not.toThrow();
  expect(renamed.find((entry) => entry.path === ".github/instructions.md")).toBe(existing[2]);
  expect(fileEdits(existing, renamed)).toEqual([{ path: "refs/one.md", content: null }, { path: "refs/renamed.md", content: "original" }]);
  const editedLegacy = renamed.map((entry) => entry.path === "token.json" ? file("token.json", "preserved edit") : entry);
  expect(() => validateWorkingOperation(existing, editedLegacy)).not.toThrow();
  expect(fileEdits(existing, editedLegacy)).toContainEqual({ path: "token.json", content: "preserved edit" });
  expect(() => validateWorkingOperation(existing, [...renamed, file(".github/new.md")])).toThrow("skill_manual_file_invalid");
});

test.each(["../escape.md", "C:/escape.md", "refs/.secret/file.md", "refs/.env.local", "refs/auth.json", "refs/key.pem", "refs/CON.txt", "refs/name.", "refs//x.md"])("unsafe %s refuses the whole operation", (path) => {
  expect(() => validateWorkingOperation(base, [...base, file(path)])).toThrow("skill_manual_file_invalid");
  expect(base.map((f) => f.path)).toEqual(["SKILL.md", "refs/one.md"]);
});

test("case/file-folder collisions and oversize files refuse without overwriting; core entrypoint is protected", async () => {
  for (const extra of [file("refs/ONE.md"), file("refs"), file("refs/one.md/child.md")]) expect(() => validateWorkingOperation(base, [...base, extra])).toThrow("skill_manual_file_conflict");
  expect(() => moveFiles(base, "refs", "refs/inside")).toThrow("skill_manual_file_invalid");
  expect(() => moveFiles(base, "refs", "REFS")).toThrow("skill_manual_file_conflict");
  expect(() => moveFiles(base, "SKILL.md", "other.md")).toThrow("skill_manual_file_invalid");
  expect(() => deleteFiles(base, "SKILL.md")).toThrow("skill_manual_file_invalid");
  await expect(readLocalFiles([local("large.md", new Uint8Array(512*1024+1))], "")).rejects.toThrow("skill_manual_file_limit");
  const unreadable = new File(["x"], "bad.md");
  Object.defineProperty(unreadable, "arrayBuffer", { value: async () => { throw Error("private host path"); } });
  await expect(readLocalFiles([local("ok.md", new Uint8Array([65])), unreadable], "")).rejects.toThrow("skill_manual_file_read_failed");
});

test("every literal file-action error producer is descriptively catalogued", () => {
  const codes = new Set(["SkillWorkingTree.ts", "SkillFileManager.tsx"].flatMap((name) => [...readFileSync(join(__dirname, name), "utf8").matchAll(/"(skill_manual_[a-z_]+)"/g)].map((match) => match[1])));
  expect(codes.size).toBeGreaterThanOrEqual(5);
  for (const code of codes) for (const field of ["title", "description", "recovery"]) expect((catalog as Record<string, Record<string, string>>)[code][field].trim()).not.toBe("");
});
