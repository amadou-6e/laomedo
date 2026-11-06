import type { editor } from "monaco-editor/editor";

function sourceOffset(source: string, line: number, column: number): number {
  let start = source.startsWith("\uFEFF") ? 1 : 0;
  const endings = /\r\n|\r|\n/g;
  for (let current = 1; current < line; current++) {
    const ending = endings.exec(source);
    if (!ending) throw new Error("Invalid editor source range");
    start = ending.index + ending[0].length;
  }
  return start + column - 1;
}

export function applySourceChanges(source: string, changes: readonly editor.IModelContentChange[]): string {
  // Monaco coordinates exclude the BOM and normalize EOLs. Project ranges back
  // onto the original text, preserving all bytes outside the edited ranges.
  const edits = changes.map(({ range, text }) => ({
    start: sourceOffset(source, range.startLineNumber, range.startColumn),
    end: sourceOffset(source, range.endLineNumber, range.endColumn), text,
  })).sort((a, b) => b.start - a.start);
  return edits.reduce((text, edit) => text.slice(0, edit.start) + edit.text + text.slice(edit.end), source);
}
