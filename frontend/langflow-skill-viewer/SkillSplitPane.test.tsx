import { render, screen, fireEvent } from "@testing-library/react";
import SkillSplitPane from "./SkillSplitPane";

beforeEach(() => {
  jest.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({ left: 100, width: 1000 } as DOMRect);
  window.PointerEvent = MouseEvent as typeof PointerEvent;
  HTMLElement.prototype.setPointerCapture = jest.fn();
  HTMLElement.prototype.hasPointerCapture = jest.fn(() => false);
});
afterEach(() => jest.restoreAllMocks());

test("navigation width changes with pointer drag and remains bounded", () => {
  render(<SkillSplitPane navigation={<p>Files and commits</p>}><p>Source or comparison</p></SkillSplitPane>);
  const separator = screen.getByRole("separator", { name: "Resize navigation pane" });
  fireEvent.pointerDown(separator, { button: 0, clientX: 380 });
  fireEvent.pointerMove(separator, { clientX: 540 });
  expect(separator).toHaveAttribute("aria-valuenow", "440");
  expect(screen.getByRole("complementary", { name: "Skill navigation" })).toHaveStyle({ width: "440px" });
  fireEvent.pointerMove(separator, { clientX: 2000 });
  expect(separator).toHaveAttribute("aria-valuenow", "600");
  fireEvent.pointerUp(separator);
});

test("separator supports keyboard resizing while keeping content visible", () => {
  render(<SkillSplitPane navigation={<p>Files and commits</p>}><p>Source or comparison</p></SkillSplitPane>);
  const separator = screen.getByRole("separator", { name: "Resize navigation pane" });
  fireEvent.keyDown(separator, { key: "ArrowRight" });
  expect(separator).toHaveAttribute("aria-valuenow", "296");
  fireEvent.keyDown(separator, { key: "Home" });
  expect(separator).toHaveAttribute("aria-valuenow", "0");
  expect(screen.getByText("Source or comparison")).toBeVisible();
});


test("drag past the collapse threshold then restore without losing navigation state", () => {
  render(<SkillSplitPane navigation={<input aria-label="File selection" defaultValue="SKILL.md" />}><p>Source</p></SkillSplitPane>);
  const separator = screen.getByRole("separator", { name: "Resize navigation pane" });
  const selection = screen.getByRole("textbox", { name: "File selection" });
  fireEvent.change(selection, { target: { value: "OVERVIEW.md" } });
  fireEvent.pointerDown(separator, { button: 0 });
  fireEvent.pointerMove(separator, { clientX: 150 });
  fireEvent.pointerUp(separator);
  expect(separator).toHaveAttribute("aria-valuenow", "0");
  expect(selection).not.toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Show skill navigation" }));
  expect(selection).toBeVisible();
  expect(separator).toHaveFocus();
  expect(selection).toHaveValue("OVERVIEW.md");
  expect(separator).toHaveAttribute("aria-valuenow", "280");
});


test("hiding from the action menu retains focus on the divider after the menu closes", async () => {
  jest.spyOn(HTMLElement.prototype, "getClientRects").mockImplementation(function (this: HTMLElement) {
    return (this.closest("aside")?.style.display === "none" ? [] : [{}]) as unknown as DOMRectList;
  });
  render(<SkillSplitPane navigation={<p>Files</p>}><p>Source</p></SkillSplitPane>);
  fireEvent.click(screen.getByLabelText("Navigation actions"));
  fireEvent.click(screen.getByRole("button", { name: "Hide navigation" }));
  await Promise.resolve();
  expect(screen.getByRole("separator", { name: "Resize navigation pane" })).toHaveFocus();
});
