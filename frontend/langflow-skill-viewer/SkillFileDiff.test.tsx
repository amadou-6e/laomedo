import { render, screen } from "@testing-library/react";
import SkillFileDiff from "./SkillFileDiff";
import * as monaco from "monaco-editor/editor";
jest.mock("@/stores/darkStore", () => ({ useDarkStore: (select: any) => select({ dark: false }) }));
jest.mock("monaco-editor/editor", () => ({ editor: {
  createModel: jest.fn(() => ({ dispose: jest.fn() })),
  createDiffEditor: jest.fn(() => ({ setModel: jest.fn(), dispose: jest.fn() })),
} }));
const file = { path: "SKILL.md", kind: "text" as const, bytes: 6, file_hash: "hash", text: "hello\n" };
beforeEach(() => jest.clearAllMocks());
test("visual editor compares full exact text and disposes models on file change", () => {
  const view = render(<SkillFileDiff path={file.path} original={file} current={{ ...file, text: "hello\nnew\n", file_hash: "new" }} />);
  expect(monaco.editor.createModel).toHaveBeenNthCalledWith(1, "hello\n", "markdown");
  expect(monaco.editor.createModel).toHaveBeenNthCalledWith(2, "hello\nnew\n", "markdown");
  expect(monaco.editor.createDiffEditor).toHaveBeenCalledWith(expect.anything(), expect.objectContaining({ readOnly: true, ignoreTrimWhitespace: false }));
  const instance = (monaco.editor.createDiffEditor as jest.Mock).mock.results[0].value;
  const model = (monaco.editor.createModel as jest.Mock).mock.results[0].value;
  view.unmount();
  expect(instance.dispose).toHaveBeenCalled(); expect(model.dispose).toHaveBeenCalled();
});
test.each(["added", "deleted"])("%s files use an empty absent side", (status) => {
  render(<SkillFileDiff path={file.path} original={status === "deleted" ? file : undefined} current={status === "added" ? file : undefined} />);
  expect(screen.getByRole("status")).toHaveTextContent(status === "added" ? "Added file" : "Deleted file");
  expect(monaco.editor.createModel).toHaveBeenNthCalledWith(status === "added" ? 1 : 2, "", "markdown");
});
test("binary files show metadata without creating an editor", () => {
  render(<SkillFileDiff path={file.path} original={{ ...file, kind: "binary", text: null }} current={file} />);
  expect(screen.getByText(/Binary file comparison unavailable/)).toBeInTheDocument();
  expect(monaco.editor.createDiffEditor).not.toHaveBeenCalled();
});
test("unchanged files remain visible", () => {
  render(<SkillFileDiff path={file.path} original={file} current={file} />);
  expect(screen.getByRole("status")).toHaveTextContent("No changes in this file");
  expect(monaco.editor.createModel).toHaveBeenCalledTimes(2);
});
