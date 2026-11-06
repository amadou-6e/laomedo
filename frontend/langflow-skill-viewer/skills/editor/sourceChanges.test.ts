import { applySourceChanges } from "./sourceChanges";
import type { editor } from "monaco-editor/editor";
const edit = (line: number, column: number, endColumn: number, text: string): editor.IModelContentChange => ({
  range: { startLineNumber: line, startColumn: column, endLineNumber: line, endColumn },
  rangeOffset: 0, rangeLength: endColumn - column, text,
});
test.each(["\uFEFFfirst\r\nsecond\nthird\r\n", "first\nsecond\r\nthird\n"])("edits preserve BOM and untouched mixed line endings", source => {
  const changed = applySourceChanges(source, [edit(2, 1, 7, "replaced")]);
  expect(changed).toBe(source.replace("second", "replaced"));
  expect(applySourceChanges(changed, [edit(2, 1, 9, "second")])).toBe(source);
});
test("simultaneous edits use original coordinates and preserve a first-line BOM", () => {
  expect(applySourceChanges("\uFEFFone\r\ntwo\n", [edit(1, 1, 4, "1"), edit(2, 1, 4, "2")])).toBe("\uFEFF1\r\n2\n");
});
test("multiline replacements preserve separators outside the range", () => {
  const change = { ...edit(1, 2, 2, "!"), range: { startLineNumber: 1, startColumn: 2, endLineNumber: 2, endColumn: 2 } };
  expect(applySourceChanges("\uFEFFone\r\ntwo\nthree\r\n", [change])).toBe("\uFEFFo!wo\nthree\r\n");
});
