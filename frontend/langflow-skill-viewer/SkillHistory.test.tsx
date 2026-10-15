import { render, screen, fireEvent, act } from "@testing-library/react";
import SkillHistory from "./SkillHistory";
import { api } from "@/controllers/API/api";
jest.mock("@/controllers/API/api", () => ({ api: { get: jest.fn() } }));
jest.mock("@/customization/utils/urls", () => ({ getBaseUrl: () => "/api/v1/" }));
const commit = { commit_id: "commit-one", parent_commit: "root", revision_id: "revision-one",
  message: "Clarify two files", created_at: "2026-10-16T00:00:00Z", files: ["SKILL.md", "reference.md"],
  editor: { kind: "agent", run_id: "run-one" }, patch: "--- base/SKILL.md\n+++ draft/SKILL.md\n+<script>hostile</script>" };
beforeEach(() => jest.clearAllMocks());

test("history opens exact commit diff and labels provenance without executing markup", async () => {
  (api.get as jest.Mock).mockImplementation((url: string) => Promise.resolve({ data: url.endsWith("/history")
    ? { skill_id: "skill", selected_revision: "revision-one", commits: [commit], next: null } : commit }));
  const { container } = render(<SkillHistory skillId="skill" revision="revision-one" />);
  fireEvent.click(await screen.findByRole("button", { name: "View diff: Clarify two files" }));
  expect(await screen.findByTestId("skill-commit-diff")).toHaveTextContent("<script>hostile</script>");
  expect(container.querySelector("script")).toBeNull();
  expect(screen.getByText("Backend-asserted; not independently runner-verified")).toBeInTheDocument();
  expect(api.get).toHaveBeenCalledTimes(2);
});

test("failed history retries and never invents a commit", async () => {
  (api.get as jest.Mock).mockRejectedValueOnce(new Error("unavailable"))
    .mockResolvedValueOnce({ data: { skill_id: "skill", selected_revision: "revision-one", commits: [], next: null } });
  render(<SkillHistory skillId="skill" revision="revision-one" />);
  await screen.findByRole("alert");
  fireEvent.click(screen.getByRole("button", { name: "Retry" }));
  await screen.findByText("No operation history for this skill.");
  expect(screen.queryByTestId("skill-commit-diff")).toBeNull();
});

test("unmounted selection cannot display a late diff", async () => {
  let finish: ((value: unknown) => void) | undefined;
  (api.get as jest.Mock).mockImplementation((url: string) => url.endsWith("/history")
    ? Promise.resolve({ data: { skill_id: "skill", selected_revision: "revision-one", commits: [commit], next: null } })
    : new Promise((resolve) => { finish = resolve; }));
  const view = render(<SkillHistory skillId="skill" revision="revision-one" />);
  fireEvent.click(await screen.findByRole("button", { name: "View diff: Clarify two files" }));
  view.unmount();
  await act(async () => { finish?.({ data: commit }); });
  expect(screen.queryByTestId("skill-commit-diff")).toBeNull();
});
