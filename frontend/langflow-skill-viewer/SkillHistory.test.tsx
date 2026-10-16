import { render, screen, fireEvent, act } from "@testing-library/react";
import CommitTree, { RevisionDiff } from "./SkillHistory";
import { api } from "@/controllers/API/api";
jest.mock("@/controllers/API/api", () => ({ api: { get: jest.fn() } }));
jest.mock("@/customization/utils/urls", () => ({ getBaseUrl: () => "/api/v1/" }));
const commit = { commit_id: "commit-one", parent_commit: "root", revision_id: "old-tree",
  message: "Clarify two files", created_at: "2026-10-16T00:00:00Z", editor: { kind: "agent", run_id: "run-one" } };
const compared = { skill_id: "skill", base_commit: commit, base_revision: "old-tree", current_revision: "current-tree",
  files: [{ path: "SKILL.md", status: "modified", binary: false }], patch: "--- a/SKILL.md\n+++ b/SKILL.md\n+<script>hostile</script>\n" };
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
  const { container } = render(<RevisionDiff skillId="skill" revision="current-tree" commit={commit} />);
  expect(await screen.findByTestId("skill-commit-diff")).toHaveTextContent("<script>hostile</script>");
  expect(container.querySelector("script")).toBeNull();
  expect(screen.getByText("Backend-asserted; not independently runner-verified")).toBeInTheDocument();
  expect(api.get).toHaveBeenCalledWith(expect.stringContaining("/current-tree/compare/commit-one"), expect.anything());
});

test("mismatched comparison fails and retries without stale content", async () => {
  (api.get as jest.Mock).mockResolvedValueOnce({ data: { ...compared, current_revision: "wrong-tree" } })
    .mockResolvedValueOnce({ data: { ...compared, files: [], patch: "" } });
  render(<RevisionDiff skillId="skill" revision="current-tree" commit={commit} />);
  await screen.findByRole("alert");
  expect(screen.queryByTestId("skill-commit-diff")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Retry" }));
  await screen.findByText("No differences from current revision.");
});

test("unmounted revision cannot display a late comparison", async () => {
  let finish: ((value: unknown) => void) | undefined;
  (api.get as jest.Mock).mockImplementation(() => new Promise((resolve) => { finish = resolve; }));
  const view = render(<RevisionDiff skillId="skill" revision="current-tree" commit={commit} />);
  view.unmount();
  await act(async () => { finish?.({ data: compared }); });
  expect(screen.queryByTestId("skill-commit-diff")).toBeNull();
});
