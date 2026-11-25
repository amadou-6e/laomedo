import { fireEvent, render, screen } from "@testing-library/react";
import ToolCalls from "./ToolCalls";

test("native compaction completion comes from the command receipt, not missing lane status", () => {
  const lanes = [{ id: "item", thread: "native", started: "2026-11-18T14:47:00Z", ended: "2026-11-18T14:47:07Z", item: { type: "contextCompaction" } }];
  const { rerender } = render(<ToolCalls lanes={lanes} names={{}} />);
  expect(screen.getByText("Outcome unavailable")).toBeVisible();
  expect(screen.queryByText("Completed")).toBeNull();
  rerender(<ToolCalls lanes={lanes} names={{}} compactionCompleted />);
  expect(screen.getByText("Context compaction")).toBeVisible();
  expect(screen.getByText("Completed")).toBeVisible();
  fireEvent.click(screen.getByText("Context compaction"));
  expect(screen.getByText("Context compaction completed.")).toBeVisible();
});
