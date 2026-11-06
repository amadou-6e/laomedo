import { useEffect, useRef } from "react";
import type { SkillFile } from "../models";
import type { SkillMatch } from "../search/SkillSearch";
import * as monaco from "monaco-editor/editor";
import "monaco-editor/internal/common/workers";
import EditorWorker from "monaco-editor/editor/editor.worker?worker";
import "monaco-editor/languages/definitions/markdown/register";
import "monaco-editor/languages/definitions/python/register";
import "monaco-editor/languages/definitions/javascript/register";
import "monaco-editor/languages/features/json/register";
import JsonWorker from "monaco-editor/language/json/json.worker?worker";
import "monaco-editor/languages/definitions/shell/register";
import { useDarkStore } from "@/stores/darkStore";

// Bundle the editor and worker locally. No Monaco CDN or remote file loader.
(self as typeof self & { MonacoEnvironment?: object }).MonacoEnvironment = {
  getWorker: (_module: string, label: string) => label === "json" ? new JsonWorker() : new EditorWorker(),
};

export default function SkillSourceEditor({ file, match, editable = false, onChange }: { file: SkillFile; match: (SkillMatch & { selection: number }) | null;
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
    <div ref={container} onKeyDown={(event) => { if (event.key !== "Escape") event.stopPropagation(); }} onKeyUp={(event) => { if (event.key !== "Escape") event.stopPropagation(); }} className="min-h-0 flex-1" data-testid="skill-file-source" aria-label={`${editable ? "Editable" : "Read-only"} source: ${file.path}`} />
  </div>;
}
