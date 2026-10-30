import { act, fireEvent, render, screen } from "@testing-library/react";
import SkillFilesModal from "./SkillFilesModal";
import { api } from "@/controllers/API/api";
import { editor } from "monaco-editor/editor";
import { useHotkeys } from "react-hotkeys-hook";
jest.mock("@/controllers/API/api", () => ({ api: { get: jest.fn(), post: jest.fn() } }));
jest.mock("@/customization/utils/urls", () => ({ getBaseUrl: () => "/api/v1/" }));
jest.mock("@/stores/darkStore", () => ({ useDarkStore: () => false }));
jest.mock("@/modals/baseModal", () => {
  const Modal = ({ open, children }: any) => open ? <div role="dialog">{children}</div> : null;
  Modal.Header = ({ children }: any) => <header>{children}</header>;
  Modal.Content = ({ children }: any) => <div>{children}</div>;
  return { __esModule: true, default: Modal };
});
jest.mock("./SkillOverview", () => ({ __esModule: true, default: () => null }));
jest.mock("./SkillNavigation", () => ({ __esModule: true, default: () => null }));
jest.mock("./SkillSplitPane", () => ({ __esModule: true, default: ({ children }: any) => <>{children}</> }));
jest.mock("./SkillHistory", () => ({ __esModule: true, default: () => null, RevisionDiff: () => null }));
jest.mock("react-markdown", () => ({ __esModule: true, default: () => null }));
jest.mock("monaco-editor/editor", () => ({ editor: {
  createModel: jest.fn(() => ({ dispose: jest.fn() })),
  create: jest.fn(),
} }));
jest.mock("monaco-editor/editor/editor.worker?worker", () => ({ __esModule: true, default: jest.fn() }), { virtual: true });
jest.mock("monaco-editor/language/json/json.worker?worker", () => ({ __esModule: true, default: jest.fn() }), { virtual: true });
const props = { skillId: "skill", revision: "current-tree", open: true, setOpen: jest.fn() };
beforeEach(() => jest.clearAllMocks());

test("current file failure is descriptive, copyable and offers no futile reload", async () => {
  (api.get as jest.Mock).mockRejectedValue({ response: { data: { detail: { code: "skill_revision_too_large" }, trace: "private-body" } } });
  render(<SkillFilesModal {...props} />);
  expect(await screen.findByRole("alert")).toHaveTextContent("exceeds the viewer limits");
  expect(screen.getByRole("button", { name: "Copy error" })).toBeVisible();
  expect(screen.queryByRole("button", { name: /Reload|Retry/ })).toBeNull();
  expect(document.body.textContent).not.toContain("private-body");
  expect(api.post).not.toHaveBeenCalled();
});

test("unknown file read failure reloads only the same selection", async () => {
  (api.get as jest.Mock).mockRejectedValue(new Error("private-body"));
  render(<SkillFilesModal {...props} />);
  await screen.findByRole("alert");
  fireEvent.click(screen.getByRole("button", { name: "Reload files" }));
  await screen.findByRole("alert");
  expect(api.get).toHaveBeenCalledTimes(2);
  expect((api.get as jest.Mock).mock.calls[0][0]).toBe((api.get as jest.Mock).mock.calls[1][0]);
  expect(api.post).not.toHaveBeenCalled();
});

test("selection changes and close ignore aborted late failures", async () => {
  let reject: ((reason: unknown) => void) | undefined;
  (api.get as jest.Mock).mockImplementationOnce(() => new Promise((_resolve, failure) => { reject = failure; }))
    .mockImplementation(() => new Promise(() => {}));
  const view = render(<SkillFilesModal {...props} />);
  const signal = (api.get as jest.Mock).mock.calls[0][1].signal;
  view.rerender(<SkillFilesModal {...props} revision="other-tree" />);
  expect(signal.aborted).toBe(true);
  await act(async () => { reject?.({ response: { data: { detail: { code: "skill_revision_unsafe" } } } }); });
  expect(screen.queryByRole("alert")).toBeNull();
  const secondSignal = (api.get as jest.Mock).mock.calls[1][1].signal;
  view.rerender(<SkillFilesModal {...props} revision="other-tree" open={false} />);
  expect(secondSignal.aborted).toBe(true);
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(api.post).not.toHaveBeenCalled();
});

test("native EditContext source keys reach Monaco but not canvas keydown or keyup shortcuts", async () => {
  const canvasDown = jest.fn(), canvasUp = jest.fn(), canvasEscape = jest.fn();
  const targetDown = jest.fn(), targetUp = jest.fn(), find = jest.fn();
  (editor.create as jest.Mock).mockImplementation((container: HTMLElement) => {
    const context = document.createElement("div");
    context.className = "native-edit-context"; context.tabIndex = 0;
    context.addEventListener("keydown", targetDown); context.addEventListener("keyup", targetUp);
    container.appendChild(context);
    return { focus: () => context.focus(), getAction: () => ({ run: find }),
      trigger: jest.fn(), dispose: () => context.remove() };
  });
  (api.get as jest.Mock).mockResolvedValue({ data: { schema_version: "laomedo.skill-inspection.v1",
    skill_id: props.skillId, revision_id: props.revision, tree_hash: props.revision,
    files: [{ path: "SKILL.md", kind: "text", text: "Read-only source", bytes: 16, file_hash: "sha256:internal-control" }] } });
  function Canvas() {
    useHotkeys("a", canvasDown, { keydown: true, keyup: false, enableOnFormTags: false });
    useHotkeys("o", canvasUp, { keydown: false, keyup: true, enableOnFormTags: false });
    useHotkeys("escape", canvasEscape);
    return <><div data-testid="canvas-target" tabIndex={0} /><SkillFilesModal {...props} /></>;
  }
  render(<Canvas />);
  const source = await screen.findByTestId("skill-file-source");
  const context = source.querySelector<HTMLDivElement>(".native-edit-context")!;
  context.focus(); expect(document.activeElement).toBe(context);
  expect((editor.create as jest.Mock).mock.calls.at(-1)[1]).toMatchObject({ readOnly: true, domReadOnly: true });
  for (const event of [{ key: "a", code: "KeyA" }, { key: "o", code: "KeyO" },
    { key: "ArrowLeft", code: "ArrowLeft" }, { key: "f", code: "KeyF", ctrlKey: true }]) {
    expect(fireEvent.keyDown(context, event)).toBe(true);
    expect(fireEvent.keyUp(context, event)).toBe(true);
  }
  expect(targetDown).toHaveBeenCalledTimes(4); expect(targetUp).toHaveBeenCalledTimes(4);
  expect(canvasDown).not.toHaveBeenCalled(); expect(canvasUp).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Find in file" })); expect(find).toHaveBeenCalledTimes(1);
  fireEvent.keyDown(context, { key: "Escape", code: "Escape" });
  fireEvent.keyUp(context, { key: "Escape", code: "Escape" }); expect(canvasEscape).toHaveBeenCalledTimes(1);
  const canvas = screen.getByTestId("canvas-target"); canvas.focus();
  fireEvent.keyDown(canvas, { key: "a", code: "KeyA" }); fireEvent.keyUp(canvas, { key: "a", code: "KeyA" });
  fireEvent.keyDown(canvas, { key: "o", code: "KeyO" }); fireEvent.keyUp(canvas, { key: "o", code: "KeyO" });
  expect(canvasDown).toHaveBeenCalledTimes(1); expect(canvasUp).toHaveBeenCalledTimes(1);
  expect(api.post).not.toHaveBeenCalled();
});
