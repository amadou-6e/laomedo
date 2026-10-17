import { useEffect, useRef } from "react";
import * as monaco from "monaco-editor/editor";
import { useDarkStore } from "@/stores/darkStore";
import type { SkillFile } from "./SkillHistory";

export default function SkillFileDiff({ path, original, current }: {
  path: string; original?: SkillFile; current?: SkillFile;
}) {
  const container = useRef<HTMLDivElement>(null);
  const dark = useDarkStore((state) => state.dark);
  const binary = original?.kind === "binary" || current?.kind === "binary";
  useEffect(() => {
    if (!container.current || binary || (!original && !current)) return;
    const extension = path.split(".").pop()?.toLowerCase();
    const language = ({ md: "markdown", py: "python", js: "javascript", mjs: "javascript", json: "json", sh: "shell" } as Record<string, string>)[extension || ""] || "plaintext";
    const before = monaco.editor.createModel(original?.text ?? "", language);
    const after = monaco.editor.createModel(current?.text ?? "", language);
    const editor = monaco.editor.createDiffEditor(container.current, {
      readOnly: true, originalEditable: false, domReadOnly: true,
      automaticLayout: true, renderSideBySide: true, enableSplitViewResizing: true,
      ignoreTrimWhitespace: false, hideUnchangedRegions: { enabled: false },
      minimap: { enabled: false }, scrollBeyondLastLine: false,
      theme: dark ? "vs-dark" : "vs", fontSize: 14,
      fontFamily: "'JetBrains Mono', monospace",
    });
    editor.setModel({ original: before, modified: after });
    return () => { editor.dispose(); before.dispose(); after.dispose(); };
  }, [path, original, current, binary, dark]);
  if (!original && !current) return <p className="p-4">Select a file.</p>;
  const status = !original ? "Added file" : !current ? "Deleted file" :
    original.file_hash === current.file_hash ? "No changes in this file" : "Modified file";
  return <div className="flex min-h-0 flex-1 flex-col" data-testid="skill-file-comparison">
    <p className="shrink-0 border-b px-4 py-1 text-sm" role="status">{status}</p>
    <div className="grid shrink-0 grid-cols-2 border-b px-4 py-1 text-xs text-muted-foreground">
      <span>Selected revision{!original && " (file absent)"}</span><span>Current{!current && " (file absent)"}</span>
    </div>
    {binary ? <div className="overflow-auto p-4 text-sm">Binary file comparison unavailable.
      <p className="break-all">Selected: {original ? `${original.bytes} bytes · ${original.file_hash}` : "Absent"}</p>
      <p className="break-all">Current: {current ? `${current.bytes} bytes · ${current.file_hash}` : "Absent"}</p>
    </div> : <div ref={container} className="min-h-0 flex-1" data-testid="skill-file-diff" aria-label={`Read-only file diff: ${path}`} />}
  </div>;
}
