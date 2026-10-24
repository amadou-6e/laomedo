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

const safeRun = "ef54c538-d747-4ea7-938e-8fccd5e29bb6";
jest.mock("@/controllers/API/api", () => ({ api: { get: jest.fn().mockResolvedValue({ data: { state: "unmanaged", can_start: false } }), post: jest.fn() } }));
jest.mock("@/customization/utils/urls", () => ({ getBaseUrl: () => "/api/v1/" }));
test("app recovery retains safe identifiers in the shared diagnostics", async () => {
  render(<NodeErrorNotice inline message={`runner_transport_failed; Laomedo run ${safeRun}; remote execution may still be active; bearer private-payload`} context={{}} />);
  await screen.findByRole("region", { name: "Local backend recovery" });
  expect(screen.getAllByText("Technical details")).toHaveLength(1);
  expect(screen.getByText(new RegExp(safeRun))).toHaveTextContent("runner_transport_failed");
  expect(screen.queryByText(/private-payload/)).toBeNull();
});
test("node popovers never mount app recovery controls", () => {
  render(<NodeErrorNotice message="runner_transport_failed" context={{}} />);
  expect(screen.queryByRole("region", { name: "Local backend recovery" })).toBeNull();
});
