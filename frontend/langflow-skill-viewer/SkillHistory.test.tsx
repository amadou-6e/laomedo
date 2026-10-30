import { render, screen, fireEvent, act } from "@testing-library/react";
import CommitTree, { RevisionDiff } from "./SkillHistory";
import { api } from "@/controllers/API/api";
jest.mock("@/controllers/API/api", () => ({ api: { get: jest.fn() } }));
jest.mock("@/customization/utils/urls", () => ({ getBaseUrl: () => "/api/v1/" }));
const commit = { commit_id: "commit-one", parent_commit: "root", revision_id: "old-tree",
  message: "Clarify two files", created_at: "2026-10-16T00:00:00Z", editor: { kind: "agent", run_id: "run-one" } };
jest.mock("./SkillFileDiff", () => ({ __esModule: true, default: (props: any) =>
  <div data-testid="visual-diff">{props.path}: {props.original?.text} / {props.current?.text}</div> }));
const oldFile = { path: "SKILL.md", kind: "text" as const, bytes: 10, file_hash: "old", text: "old contents" };
const currentFile = { ...oldFile, file_hash: "current", text: "<script>hostile</script>" };
const compared = { schema_version: "laomedo.skill-inspection.v1", skill_id: "skill", revision_id: "old-tree", tree_hash: "old-tree", files: [oldFile] };
const onFiles = jest.fn();
const props = { skillId: "skill", revision: "current-tree", commit, path: "SKILL.md", current: currentFile, onFiles };
beforeEach(() => jest.clearAllMocks());

test("commit graph selects revision without requesting the old per-commit patch", async () => {
  const select = jest.fn();
  (api.get as jest.Mock).mockResolvedValue({ data: { skill_id: "skill", selected_revision: "current-tree", commits: [commit], next: null } });
  render(<CommitTree skillId="skill" revision="current-tree" selected="" onSelect={select} />);
  fireEvent.click(await screen.findByRole("button", { name: "Compare revision: Clarify two files" }));
  expect(select).toHaveBeenCalledWith(commit);
  expect(api.get).toHaveBeenCalledTimes(1);
  expect(screen.queryByRole("button", { name: "History", exact: true })).toBeNull();
});

test("comparison pins direction, labels provenance and renders hostile diff as text", async () => {
  (api.get as jest.Mock).mockResolvedValue({ data: compared });
  const { container } = render(<RevisionDiff {...props} />);
  expect(await screen.findByTestId("visual-diff")).toHaveTextContent("<script>hostile</script>");
  expect(container.querySelector("script")).toBeNull();
  expect(screen.getByText("Backend-asserted; not independently runner-verified")).toBeInTheDocument();
  expect(api.get).toHaveBeenCalledWith(expect.stringContaining("/skill/old-tree"), expect.anything());
});

test("mismatched comparison fails and retries without stale content", async () => {
  (api.get as jest.Mock).mockResolvedValueOnce({ data: { ...compared, tree_hash: "wrong-tree" } })
    .mockResolvedValueOnce({ data: compared });
  render(<RevisionDiff {...props} />);
  await screen.findByRole("alert");
  expect(screen.queryByTestId("visual-diff")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Reload files" }));
  await screen.findByTestId("visual-diff");
});

test("unmounted revision cannot display a late comparison", async () => {
  let finish: ((value: unknown) => void) | undefined;
  (api.get as jest.Mock).mockImplementation(() => new Promise((resolve) => { finish = resolve; }));
  const view = render(<RevisionDiff {...props} />);
  view.unmount();
  await act(async () => { finish?.({ data: compared }); });
  expect(screen.queryByTestId("visual-diff")).toBeNull();
});

test("switching files retains the revision and does not refetch or render an aggregate patch", async () => {
  (api.get as jest.Mock).mockResolvedValue({ data: compared });
  const view = render(<RevisionDiff {...props} />);
  await screen.findByTestId("visual-diff");
  view.rerender(<RevisionDiff {...props} path="references/new.md" current={{ ...currentFile, path: "references/new.md", text: "new file" }} />);
  expect(screen.getByTestId("visual-diff")).toHaveTextContent("references/new.md: / new file");
  expect(api.get).toHaveBeenCalledTimes(1);
  expect(screen.queryByText(/diff --git/)).toBeNull();
  expect(onFiles).toHaveBeenCalledWith([oldFile]);
});

test("history failure uses the shared read-only explanation and reloads only history", async () => {
  (api.get as jest.Mock).mockRejectedValueOnce({ response: { data: { detail: { code: "skill_history_unavailable", trace: "private-trace" } } } })
    .mockResolvedValueOnce({ data: { skill_id: "skill", selected_revision: "current-tree", commits: [commit], next: null } });
  render(<CommitTree skillId="skill" revision="current-tree" selected="" onSelect={jest.fn()} />);
  expect(await screen.findByRole("alert")).toHaveTextContent("Skill history could not be loaded");
  expect(document.body.textContent).not.toContain("private-trace");
  fireEvent.click(screen.getByRole("button", { name: "Reload history" }));
  await screen.findByRole("button", { name: "Compare revision: Clarify two files" });
  expect(api.get).toHaveBeenCalledTimes(2);
  expect((api.get as jest.Mock).mock.calls.every(([url]) => url.endsWith("/history"))).toBe(true);
});

test("unsafe historical revision has no reload and no stale diff", async () => {
  (api.get as jest.Mock).mockRejectedValue({ response: { data: { detail: { code: "skill_revision_unsafe" } } } });
  render(<RevisionDiff {...props} />);
  expect(await screen.findByRole("alert")).toHaveTextContent("cannot be safely displayed");
  expect(screen.queryByRole("button", { name: /Reload|Retry/ })).toBeNull();
  expect(screen.queryByTestId("visual-diff")).toBeNull();
  expect(onFiles).toHaveBeenCalledWith([]);
});

test("selection change ignores an aborted comparison failure", async () => {
  let reject: ((reason: unknown) => void) | undefined;
  (api.get as jest.Mock).mockImplementationOnce(() => new Promise((_resolve, failure) => { reject = failure; }))
    .mockResolvedValueOnce({ data: { ...compared, revision_id: "new-tree", tree_hash: "new-tree" } });
  const view = render(<RevisionDiff {...props} />);
  const signal = (api.get as jest.Mock).mock.calls[0][1].signal;
  view.rerender(<RevisionDiff {...props} commit={{ ...commit, commit_id: "new-commit", revision_id: "new-tree" }} />);
  expect(signal.aborted).toBe(true);
  await screen.findByTestId("visual-diff");
  await act(async () => { reject?.({ response: { data: { detail: { code: "skill_revision_unsafe" } } } }); });
  expect(screen.queryByRole("alert")).toBeNull();
  expect(screen.getByTestId("visual-diff")).toBeInTheDocument();
});
