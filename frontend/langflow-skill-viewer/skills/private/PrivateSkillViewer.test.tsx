import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import PrivateSkillViewer from "./PrivateSkillViewer";
import { privateSkillRequest, subscribePrivateInvalidation } from "./api";

jest.mock("./api", () => ({ privateSkillRequest: jest.fn(), subscribePrivateInvalidation: jest.fn(() => () => {}) }));
jest.mock("@/components/laomedoGitHubConnections/api", () => ({ ConnectionFailure: class extends Error { constructor(public code: string) { super(code); } } }));
jest.mock("@/modals/baseModal", () => {
  const Modal = ({ children }: any) => <div role="dialog">{children}</div>;
  Modal.Header = ({ children }: any) => <header>{children}</header>;
  Modal.Content = ({ children }: any) => <main>{children}</main>;
  return { __esModule: true, default: Modal };
});
jest.mock("@/components/laomedoErrors/ErrorExplanation", () => ({ __esModule: true, default: () => <p>Access refused</p> }));
jest.mock("@/components/laomedoErrors/nodeErrors", () => ({ describeNodeFailure: (code: string) => ({ code }) }));
jest.mock("../workspace/SkillSplitPane", () => ({ __esModule: true, default: ({ navigation, children }: any) => <div>{navigation}{children}</div> }));
jest.mock("../editor/SkillBinaryPreview", () => ({ __esModule: true, default: () => <p>Binary preview</p> }));
const call = privateSkillRequest as jest.Mock;
const revision = "sha256:" + "a".repeat(64);
const snapshot = { schema_version: "laomedo.skill-inspection.v1", skill_id: "private-id", revision_id: revision, tree_hash: revision,
  files: [{ path: "SKILL.md", kind: "text", text: "Private retained content", bytes: 24, file_hash: revision }] };
const props = { selection: { connectionId: "explicit-connection", repositoryId: 456 }, skillId: "private-id", revision, setOpen: jest.fn() };
beforeEach(() => { jest.clearAllMocks(); call.mockImplementation((action: string) => Promise.resolve(action === "inspect" ? snapshot : { origins: [] })); });

test("private viewer uses private reads only and clears warm files on invalidation", async () => {
  render(<PrivateSkillViewer {...props} />);
  await screen.findByText("Private retained content");
  expect(call.mock.calls.map((args) => args[0])).toEqual(["inspect", "history"]);
  act(() => (subscribePrivateInvalidation as jest.Mock).mock.calls[0][0]());
  expect(screen.queryByText("Private retained content")).toBeNull();
  expect(screen.getByText("Access refused")).toBeVisible();
});

test("late in-flight private bytes cannot repopulate an invalidated view", async () => {
  let finish: (value: unknown) => void = () => {};
  call.mockImplementation((action: string) => action === "inspect" ? new Promise((resolve) => { finish = resolve; }) : Promise.resolve({ origins: [] }));
  render(<PrivateSkillViewer {...props} />);
  await waitFor(() => expect(call).toHaveBeenCalledTimes(2));
  act(() => (subscribePrivateInvalidation as jest.Mock).mock.calls[0][0]());
  await act(async () => finish(snapshot));
  expect(screen.queryByText("Private retained content")).toBeNull();
});

test("identity mismatch clears all content rather than falling back", async () => {
  call.mockImplementation((action: string) => Promise.resolve(action === "inspect" ? { ...snapshot, skill_id: "other" } : { origins: [] }));
  render(<PrivateSkillViewer {...props} />);
  await screen.findByText("Access refused");
  expect(screen.queryByText("Private retained content")).toBeNull();
  expect(call).toHaveBeenCalledTimes(2);
  fireEvent.click(screen.getByRole("button", { name: "Refresh access" }));
  await waitFor(() => expect(call).toHaveBeenCalledTimes(4));
});
