import { act, fireEvent, render, screen } from "@testing-library/react";
import SkillInspectionError, { describeInspectionFailure } from "./SkillInspectionError";

test.each(["invalid_skill_id", "immutable_skill_revision_required", "skill_revision_unavailable", "skill_revision_unsafe", "skill_revision_too_large"])("%s is explained without a futile reload", (code) => {
  const failure = describeInspectionFailure({ response: { data: { detail: { code, raw: "private-body" } } } });
  const { container } = render(<SkillInspectionError failure={failure} onReload={jest.fn()} reloadLabel="Reload files" />);
  expect(screen.getByRole("heading")).toHaveTextContent(failure.title);
  expect(screen.getByText("Technical details").closest("details")).not.toHaveAttribute("open");
  expect(container.querySelector("pre")).toHaveTextContent(code);
  expect(screen.queryByRole("button", { name: /Reload|Retry/ })).toBeNull();
  expect(document.querySelector("#laomedo-error-popup-stack")).toBeNull();
  expect(container).not.toHaveTextContent("private-body");
});

test("unknown read errors use a neutral viewer fallback and safe copy", async () => {
  const writeText = jest.fn().mockResolvedValue(undefined), reload = jest.fn();
  Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
  const failure = describeInspectionFailure({ response: { data: { detail: { code: "future_inspection_condition", trace: "secret-trace" }, payload: "private-body" } } });
  render(<SkillInspectionError failure={failure} onReload={reload} reloadLabel="Reload files" />);
  expect(screen.getByRole("heading")).toHaveTextContent("Skill files could not be loaded");
  expect(screen.getByText(/reason has not been established/)).toBeVisible();
  expect(screen.queryByText(/runner/)).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Copy error" }));
  await act(async () => {});
  expect(writeText).toHaveBeenCalledTimes(1);
  expect(writeText.mock.calls[0][0]).toContain('"code": "future_inspection_condition"');
  expect(writeText.mock.calls[0][0]).not.toMatch(/secret-trace|private-body/);
  expect(screen.getByRole("status")).toHaveClass("sr-only");
  fireEvent.click(screen.getByRole("button", { name: "Reload files" }));
  expect(reload).toHaveBeenCalledTimes(1);
});

test.each(["Bearer secret-value", { payload: "private-body" }, null])("unsafe failure values do not leak", (code) => {
  const value = describeInspectionFailure({ response: { data: { detail: { code } } } });
  expect(JSON.stringify(value)).not.toMatch(/secret-value|private-body/);
  expect(value.description).toContain("reason has not been established");
});
