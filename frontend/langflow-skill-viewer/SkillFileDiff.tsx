import { useEffect, useRef, useState } from "react";
import * as monaco from "monaco-editor/editor";
import { useDarkStore } from "@/stores/darkStore";
import type { SkillFile } from "./SkillHistory";

export type DiffRow = { kind: "context" | "added" | "deleted"; old: number | null; current: number | null; text: string };
export function diffRows(before: string[], after: string[], changes: monaco.editor.ILineChange[]): DiffRow[] {
  const rows: DiffRow[] = [];
  let old = 1, current = 1;
  for (const change of changes) {
    const startOld = change.originalEndLineNumber === 0 ? change.originalStartLineNumber + 1 : change.originalStartLineNumber;
    const startCurrent = change.modifiedEndLineNumber === 0 ? change.modifiedStartLineNumber + 1 : change.modifiedStartLineNumber;
    while (old < startOld && current < startCurrent) {
      rows.push({ kind: "context", old: old++, current, text: after[current++ - 1] });
    }
    for (let line = startOld; line <= change.originalEndLineNumber; line++)
      rows.push({ kind: "deleted", old: line, current: null, text: before[line - 1] });
    for (let line = startCurrent; line <= change.modifiedEndLineNumber; line++)
      rows.push({ kind: "added", old: null, current: line, text: after[line - 1] });
    old = change.originalEndLineNumber === 0 ? startOld : change.originalEndLineNumber + 1;
    current = change.modifiedEndLineNumber === 0 ? startCurrent : change.modifiedEndLineNumber + 1;
  }
  while (current <= after.length) rows.push({ kind: "context", old: old++, current, text: after[current++ - 1] });
  return rows;
}

function FileRows({ rows, oldCount, currentCount }: { rows: DiffRow[]; oldCount: number; currentCount: number }) {
  const viewport = useRef<HTMLDivElement>(null);
  const [scrollTop, setScrollTop] = useState(0);
  const [height, setHeight] = useState(500);
  const lineHeight = 24;
  const start = Math.max(0, Math.floor(scrollTop / lineHeight) - 12);
  const end = Math.min(rows.length, Math.ceil((scrollTop + height) / lineHeight) + 12);
  const columns = `calc(${String(oldCount).length}ch + 4px) calc(${String(currentCount).length}ch + 4px) 24px max-content`;
  useEffect(() => {
    if (!viewport.current || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(([entry]) => setHeight(entry.contentRect.height));
    observer.observe(viewport.current);
    return () => observer.disconnect();
  }, []);
  return <div className="flex min-h-0 flex-1 flex-col" data-testid="skill-file-diff">
    <div className="grid shrink-0 border-b border-slate-400 font-mono text-xs" style={{ gridTemplateColumns: columns }} aria-hidden="true">
      <span className="border-r border-slate-400 text-center" title="Selected revision line">O</span>
      <span className="text-center" title="Current revision line">N</span><span /><span />
    </div>
    <div ref={viewport} tabIndex={0} role="region" aria-label="Read-only file changes" className="min-h-0 flex-1 overflow-auto"
      onScroll={(event) => setScrollTop(event.currentTarget.scrollTop)}>
      <div className="relative min-w-full" style={{ height: rows.length * lineHeight }}>
        {rows.slice(start, end).map((row, offset) => <div key={start + offset} data-diff-kind={row.kind}
          className="absolute grid min-w-full font-mono text-sm" style={{ top: (start + offset) * lineHeight, height: lineHeight,
            lineHeight: `${lineHeight}px`, width: "max-content", gridTemplateColumns: columns,
            background: row.kind === "added" ? "#dcfce7" : row.kind === "deleted" ? "#fee2e2" : undefined,
            color: row.kind === "context" ? undefined : "#111827" }}>
          {row.kind === "context" && row.old === row.current ? <span data-testid="single-line-index" className="pr-1 text-right text-muted-foreground" style={{ gridColumn: "1 / span 2" }}>{row.current}</span> : <>
            <span data-testid="old-line-index" aria-label={`Old line ${row.old ?? "absent"}`} className="border-r border-slate-400 pr-1 text-right">{row.old ?? ""}</span>
            <span data-testid="new-line-index" aria-label={`Current line ${row.current ?? "absent"}`} className="pr-1 text-right">{row.current ?? ""}</span>
          </>}
          <span aria-label={row.kind === "added" ? "Added" : row.kind === "deleted" ? "Deleted" : undefined}
            data-testid="diff-sign" className="text-center font-bold" style={{ fontSize: 18, color: row.kind === "added" ? "#166534" : "#991b1b" }}>{row.kind === "added" ? "+" : row.kind === "deleted" ? "−" : ""}</span>
          <code className="whitespace-pre pr-6" style={{ font: "inherit" }}>{row.text || " "}</code>
        </div>)}
      </div>
    </div>
  </div>;
}

export default function SkillFileDiff({ path, original, current }: {
  path: string; original?: SkillFile; current?: SkillFile;
}) {
  const container = useRef<HTMLDivElement>(null);
  const [rows, setRows] = useState<DiffRow[] | null>(null);
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
      automaticLayout: true, renderSideBySide: false,
      lineNumbersMinChars: 1, lineDecorationsWidth: 4, folding: false,
      glyphMargin: false, renderFinalNewline: "off",
      ignoreTrimWhitespace: false, hideUnchangedRegions: { enabled: false },
      minimap: { enabled: false }, scrollBeyondLastLine: false,
      theme: dark ? "vs-dark" : "vs", fontSize: 14,
      fontFamily: "'JetBrains Mono', monospace",
    });
    let disposed = false;
    setRows(null);
    const updateRows = () => {
      const changes = editor.getLineChanges();
      if (disposed || changes === null) return;
      const originalLines = original ? before.getLinesContent() : [];
      const currentLines = current ? after.getLinesContent() : [];
      setRows(!original ? currentLines.map((text, index) => ({ kind: "added", old: null, current: index + 1, text })) :
        !current ? originalLines.map((text, index) => ({ kind: "deleted", old: index + 1, current: null, text })) :
          diffRows(originalLines, currentLines, changes));
    };
    const diffListener = editor.onDidUpdateDiff(updateRows);
    editor.setModel({ original: before, modified: after });
    updateRows();
    return () => { disposed = true; diffListener.dispose(); editor.dispose(); before.dispose(); after.dispose(); };

  }, [path, original, current, binary, dark]);
  if (!original && !current) return <p className="p-4">Select a file.</p>;
  const status = !original ? "Added file" : !current ? "Deleted file" :
    original.file_hash === current.file_hash ? "No changes in this file" : "Modified file";
  const endings = (text: string) => {
    const crlf = (text.match(/\r\n/g) || []).length;
    const lf = (text.match(/\n/g) || []).length - crlf;
    const cr = (text.match(/\r(?!\n)/g) || []).length;
    return [crlf && `${crlf} CRLF`, lf && `${lf} LF`, cr && `${cr} CR`].filter(Boolean).join(", ") || "None";
  };
  const endingNotice = !binary && original && current && original.text !== current.text &&
    (endings(original.text || "") !== endings(current.text || "") ||
      original.text?.replace(/\r\n/g, "\n") === current.text?.replace(/\r\n/g, "\n"));
  return <div className="flex min-h-0 flex-1 flex-col" data-testid="skill-file-comparison">
    <p className="shrink-0 border-b px-4 py-1 text-sm" role="status">{status}</p>
    {endingNotice && <p className="shrink-0 px-4 py-1 text-xs text-muted-foreground">Line endings: selected {endings(original.text || "")}; current {endings(current.text || "")}. Endings are not highlighted in the editor.</p>}
    <div className="shrink-0 border-b px-4 py-1 text-xs text-muted-foreground">
      Selected revision{!original && " (file absent)"} → Current{!current && " (file absent)"}
    </div>
    {binary ? <div className="overflow-auto p-4 text-sm">Binary file comparison unavailable.
      <p className="break-all">Selected: {original ? `${original.bytes} bytes · ${original.file_hash}` : "Absent"}</p>
      <p className="break-all">Current: {current ? `${current.bytes} bytes · ${current.file_hash}` : "Absent"}</p>
    </div> : <>
      <div ref={container} aria-hidden="true" className="pointer-events-none absolute overflow-hidden opacity-0" style={{ width: 1, height: 1, visibility: "hidden" }} />
      {rows ? <FileRows rows={rows} oldCount={original?.text?.split(/\r\n|\r|\n/).length || 1} currentCount={current?.text?.split(/\r\n|\r|\n/).length || 1} /> :
        <p role="status" className="p-4">Computing file changes…</p>}

    </>}
  </div>;
}
