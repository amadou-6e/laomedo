import { act, fireEvent, render, renderHook, screen } from "@testing-library/react";
import SkillNavigation, { useSkillNavigation } from "./SkillNavigation";

function NavigationExample() {
  const state = useSkillNavigation("skill:revision", ["SKILL.md", "references/nested/rules.md"]);
  return <>
    <button onClick={state.toggleAll}>{state.allOpen ? "Collapse all" : "Open all"}</button>
    <SkillNavigation open={state.open} onToggle={state.toggleSection}
      files={<input aria-label="Selected file" defaultValue="SKILL.md" />} commits={<p>Selected commit</p>} />
  </>;
}

test("individual chevrons preserve selected content without redundant section menus", () => {
  render(<NavigationExample />);
  expect(screen.queryByLabelText("Files actions")).not.toBeInTheDocument();
  expect(screen.queryByLabelText("Commits actions")).not.toBeInTheDocument();
  const file = screen.getByRole("textbox", { name: "Selected file" });
  fireEvent.change(file, { target: { value: "references/nested/rules.md" } });
  fireEvent.click(screen.getByRole("button", { name: "Files", exact: true }));
  expect(file).not.toBeVisible();
  expect(screen.getByText("Selected commit")).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Open all" }));
  expect(file).toBeVisible();
  expect(file).toHaveValue("references/nested/rules.md");
  fireEvent.click(screen.getByRole("button", { name: "Collapse all" }));
  expect(file).not.toBeVisible();
  expect(screen.getByText("Selected commit")).not.toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Open all" }));
  expect(file).toHaveValue("references/nested/rules.md");
});

test("bulk action includes nested folders and resolves a mixed state to open all", () => {
  const { result } = renderHook(() => useSkillNavigation("skill:revision", ["SKILL.md", "references/nested/rules.md"]));
  act(() => result.current.showFind());
  act(() => result.current.toggleFolder("references/nested"));
  expect(result.current.allOpen).toBe(false);
  act(() => result.current.toggleAll());
  expect(result.current.collapsedFolders.size).toBe(0);
  expect(result.current.allOpen).toBe(true);
  act(() => result.current.toggleAll());
  expect(result.current.open).toEqual({ Find: false, Files: false, Commits: false });
  expect([...result.current.collapsedFolders]).toEqual(["references", "references/nested",
    "search:folder:references", "search:folder:references/nested", "search:file:SKILL.md", "search:file:references/nested/rules.md"]);
  act(() => result.current.toggleSection("Files"));
  expect(result.current.allOpen).toBe(false);
  act(() => result.current.toggleAll());
  expect(result.current.allOpen).toBe(true);
});

test("no-folder skills use section state, ignore stale historical folders, and reset on identity changes", () => {
  const { result, rerender } = renderHook(({ identity, paths }) => useSkillNavigation(identity, paths), { initialProps: { identity: "one", paths: ["SKILL.md", "old/rules.md"] } });
  act(() => result.current.showFind());
  act(() => result.current.toggleFolder("old"));
  rerender({ identity: "one", paths: ["SKILL.md"] });
  expect(result.current.allOpen).toBe(true);
  act(() => result.current.toggleAll());
  expect(result.current.allOpen).toBe(false);
  rerender({ identity: "two", paths: ["SKILL.md"] });
  expect(result.current.allOpen).toBe(false);
  expect(result.current.open.Find).toBe(false);
});
