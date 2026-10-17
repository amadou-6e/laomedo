import { render, screen, within } from "@testing-library/react";
import SkillFileDiff, { diffRows } from "./SkillFileDiff";
import * as monaco from "monaco-editor/editor";
let mockChanges: any[] = [];
jest.mock("@/stores/darkStore", () => ({ useDarkStore: (select: any) => select({ dark: false }) }));
jest.mock("monaco-editor/editor", () => ({ editor: {
  createModel: jest.fn((text) => ({ dispose: jest.fn(), getLinesContent: () => text.split(/\r\n|\r|\n/) })),
  createDiffEditor: jest.fn(() => ({ setModel: jest.fn(), dispose: jest.fn(),
    getLineChanges: () => mockChanges,
    onDidUpdateDiff: jest.fn(() => ({ dispose: jest.fn() })) })),
} }));
const file = { path: "SKILL.md", kind: "text" as const, bytes: 6, file_hash: "hash", text: "hello\n" };
beforeEach(() => { jest.clearAllMocks(); mockChanges = []; });

test("addition rows have explicit old/new cells and a readable plus; context has one index", () => {
  mockChanges = [{ originalStartLineNumber: 1, originalEndLineNumber: 0, modifiedStartLineNumber: 2, modifiedEndLineNumber: 2 }];
  const view = render(<SkillFileDiff path={file.path} original={file} current={{ ...file, text: "hello\nnew\n", file_hash: "new" }} />);
  const addition = view.container.querySelector('[data-diff-kind="added"]')! as HTMLElement;
  expect(within(addition).getByTestId("old-line-index")).toHaveTextContent("—");
  expect(within(addition).getByTestId("new-line-index")).toHaveTextContent("2");
  expect(within(addition).getByLabelText("Added")).toHaveTextContent("+");
  expect(within(addition).getByLabelText("Added")).toHaveStyle({ fontSize: "18px" });
  const context = view.container.querySelector('[data-diff-kind="context"]')! as HTMLElement;
  expect(within(context).getByTestId("single-line-index")).toHaveTextContent("1");
  expect(within(context).queryByTestId("old-line-index")).toBeNull();
  expect(monaco.editor.createModel).toHaveBeenNthCalledWith(1, "hello\n", "markdown");
  const instance = (monaco.editor.createDiffEditor as jest.Mock).mock.results[0].value;
  const model = (monaco.editor.createModel as jest.Mock).mock.results[0].value;
  const listener = instance.onDidUpdateDiff.mock.results[0].value;
  view.unmount();
  expect(instance.dispose).toHaveBeenCalled(); expect(model.dispose).toHaveBeenCalled(); expect(listener.dispose).toHaveBeenCalled();
});
test("deleted file has an old index, absent current index and readable minus", () => {
  render(<SkillFileDiff path={file.path} original={file} />);
  expect(screen.getByRole("status")).toHaveTextContent("Deleted file");
  expect(screen.getAllByTestId("old-line-index")[0]).toHaveTextContent("1");
  expect(screen.getAllByTestId("new-line-index")[0]).toHaveTextContent("—");
  expect(screen.getAllByLabelText("Deleted")[0]).toHaveTextContent("−");
});
test("replacement preserves old/new indexes and shifted unchanged lines", () => {
  const changes = [{ originalStartLineNumber: 2, originalEndLineNumber: 2, modifiedStartLineNumber: 2, modifiedEndLineNumber: 3 }];
  const rows = diffRows(["a", "old", "tail"], ["a", "new", "extra", "tail"], changes);
  expect(rows.map(({ kind, old, current, text }) => [kind, old, current, text])).toEqual([
    ["context", 1, 1, "a"], ["deleted", 2, null, "old"], ["added", null, 2, "new"],
    ["added", null, 3, "extra"], ["context", 3, 4, "tail"],
  ]);
});
test("pure deletion at start does not lose following context", () => {
  expect(diffRows(["old", "keep"], ["keep"], [{ originalStartLineNumber: 1, originalEndLineNumber: 1, modifiedStartLineNumber: 0, modifiedEndLineNumber: 0 }]).map((row) => row.kind)).toEqual(["deleted", "context"]);
});
test("large files render a bounded visible window", () => {
  const text = Array.from({ length: 10000 }, (_, index) => `line ${index}`).join("\n");
  const { container } = render(<SkillFileDiff path={file.path} current={{ ...file, text }} />);
  expect(container.querySelectorAll('[data-diff-kind="added"]').length).toBeLessThan(60);
});
test("binary files show metadata without creating an editor", () => {
  render(<SkillFileDiff path={file.path} original={{ ...file, kind: "binary", text: null }} current={file} />);
  expect(screen.getByText(/Binary file comparison unavailable/)).toBeInTheDocument();
  expect(monaco.editor.createDiffEditor).not.toHaveBeenCalled();
});
test("unchanged files keep one index per row", () => {
  render(<SkillFileDiff path={file.path} original={file} current={file} />);
  expect(screen.getByRole("status")).toHaveTextContent("No changes in this file");
  expect(screen.queryByTestId("old-line-index")).toBeNull();
  expect(screen.getAllByTestId("single-line-index").length).toBeGreaterThan(0);
});
test("line-ending-only changes disclose the difference hidden by Monaco", () => {
  render(<SkillFileDiff path={file.path} original={{ ...file, text: "hello\r\n" }} current={{ ...file, file_hash: "other" }} />);
  expect(screen.getByText(/Line endings: selected 1 CRLF; current 1 LF/)).toBeInTheDocument();
});
