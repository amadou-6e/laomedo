import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import NodeErrorNotice from "./NodeErrorNotice";
jest.mock("@/components/ui/popover", () => ({
  Popover: ({ children }: any) => <div>{children}</div>,
  PopoverTrigger: ({ children }: any) => <div>{children}</div>,
  PopoverContent: ({ children }: any) => <section>{children}</section>,
}));

test("explains the operation, hides details initially and copies only safe diagnostics", async () => {
  const writeText = jest.fn().mockResolvedValue(undefined);
  Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
  render(<NodeErrorNotice message="prior_run_required" context={{ nodeId: "agent", nodeType: "LaomedoCodexAgent", operation: "resume" }} />);
  expect(screen.getByText("No previous run is available")).toBeVisible();
  expect(screen.getByText(/LaomedoCodexAgent/)).toHaveTextContent("resume");
  const details = screen.getByText("Technical details").closest("details")!;
  expect(details).not.toHaveAttribute("open");
  fireEvent.click(screen.getByText("Technical details"));
  fireEvent.click(screen.getByRole("button", { name: "Copy diagnostics" }));
  await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Copied"));
  expect(JSON.parse(writeText.mock.calls[0][0])).toEqual({ code: "prior_run_required", node_id: "agent", operation: "resume" });
});

test("clipboard failure gives an honest manual-copy fallback", async () => {
  Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText: jest.fn().mockRejectedValue(new Error("denied")) } });
  render(<NodeErrorNotice message="runner_status_unknown" context={{ nodeType: "LaomedoCodexAgent" }} />);
  fireEvent.click(screen.getByText("Technical details"));
  fireEvent.click(screen.getByRole("button", { name: "Copy diagnostics" }));
  await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Copy unavailable"));
  expect(screen.getByRole("status")).not.toHaveTextContent(/^Copied$/);
});
