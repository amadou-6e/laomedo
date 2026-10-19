import { fireEvent, render, screen } from "@testing-library/react";
import SkillNavigation from "./SkillNavigation";

test("either section collapses without unmounting its selected content", () => {
  render(<SkillNavigation files={<input aria-label="Selected file" defaultValue="SKILL.md" />} commits={<p>Selected commit</p>} />);
  const file = screen.getByRole("textbox", { name: "Selected file" });
  fireEvent.change(file, { target: { value: "OVERVIEW.md" } });
  fireEvent.click(screen.getByRole("button", { name: "Files", exact: true }));
  expect(file).not.toBeVisible();
  expect(screen.getByText("Selected commit")).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Files", exact: true }));
  expect(file).toBeVisible();
  expect(file).toHaveValue("OVERVIEW.md");
  fireEvent.click(screen.getByRole("button", { name: "Commits", exact: true }));
  expect(screen.getByText("Selected commit")).not.toBeVisible();
});

test("section actions let one section take the column and restore both", () => {
  render(<SkillNavigation files={<p>File content</p>} commits={<p>Commit content</p>} />);
  fireEvent.click(screen.getByLabelText("Commits actions"));
  fireEvent.click(screen.getByRole("button", { name: "Expand only commits" }));
  expect(screen.getByText("File content")).not.toBeVisible();
  expect(screen.getByText("Commit content")).toBeVisible();
  fireEvent.click(screen.getByLabelText("Files actions"));
  fireEvent.click(screen.getAllByRole("button", { name: "Expand both sections" })[0]);
  expect(screen.getByText("File content")).toBeVisible();
});
