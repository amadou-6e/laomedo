import { act, fireEvent, render, screen } from "@testing-library/react";
import SkillFilesModal from "./SkillFilesModal";
import { api } from "@/controllers/API/api";
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
jest.mock("monaco-editor/editor", () => ({}));
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
