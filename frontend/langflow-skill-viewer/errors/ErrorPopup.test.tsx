import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import ErrorPopup from "./ErrorPopup";
const context = { nodeId: "agent", nodeType: "LaomedoCodexAgent", operation: "resume" };
test("copies the explanation and safe diagnostics in a separate footer without dismissing", async () => {
  const writeText = jest.fn().mockResolvedValue(undefined), dismiss = jest.fn();
  Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
  render(<ErrorPopup message="prior_run_required; bearer private-payload" context={context} onDismiss={dismiss} />);
  const card = screen.getByRole("region", { name: "Error details" });
  expect(card.parentElement?.id).toBe("laomedo-error-popup-stack");
  expect(card.parentElement).toHaveAttribute("aria-live", "assertive");
  expect(screen.getByText("Technical details").closest("details")).not.toHaveAttribute("open");
  fireEvent.click(screen.getByRole("button", { name: "Copy error" }));
  await screen.findByText("Copied");
  expect(writeText.mock.calls[0][0]).toContain('"code": "prior_run_required"');
  expect(writeText.mock.calls[0][0]).toContain("No previous run is available");
  expect(writeText.mock.calls[0][0]).not.toContain("private-payload");
  expect(dismiss).not.toHaveBeenCalled();
  expect(screen.getByRole("button", { name: "Copied" }).closest("header")).toBeTruthy();
  expect(screen.getByRole("status")).toHaveClass("sr-only");
  fireEvent.keyDown(card, { key: "Escape" }); expect(dismiss).toHaveBeenCalledTimes(1);
});
test("clipboard rejection offers selectable text and never claims success", async () => {
  Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText: jest.fn().mockRejectedValue(new Error("denied")) } });
  render(<ErrorPopup message="future_error_240; private-payload" context={context} onDismiss={() => {}} />);
  fireEvent.click(screen.getByRole("button", { name: "Copy error" }));
  await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Copy unavailable"));
  expect(screen.queryByText("Copied")).toBeNull(); expect(document.body.textContent).not.toContain("private-payload");
});

test.each(["github_pat_" + "a".repeat(36), "GITHUB_PAT_" + "A".repeat(36)])("credential-shaped node identifiers are absent from popup DOM and copy: %s", async (nodeId) => {
  const writeText = jest.fn().mockResolvedValue(undefined);
  Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
  const { container } = render(<ErrorPopup message="skill_operation_invalid" context={{ nodeId }} onDismiss={() => {}} />);
  expect(container.textContent).not.toContain(nodeId);
  expect(document.body.textContent).not.toContain(nodeId);
  expect(screen.getByText(/"code": "skill_operation_invalid"/)).not.toHaveTextContent("node_id");
  fireEvent.click(screen.getByRole("button", { name: "Copy error" }));
  await screen.findByText("Copied");
  expect(writeText).toHaveBeenCalledTimes(1);
  expect(writeText.mock.calls[0][0]).not.toContain(nodeId);
  expect(writeText.mock.calls[0][0]).not.toContain('"node_id"');
  expect(writeText.mock.calls[0][0]).toContain('"code": "skill_operation_invalid"');
});
test("concurrent cards share one stack and removing one preserves the other", () => {
  const view = render(<><ErrorPopup message="prior_run_required" onDismiss={() => {}} /><ErrorPopup message="runner_status_unknown" onDismiss={() => {}} /></>);
  expect(document.querySelectorAll("#laomedo-error-popup-stack")).toHaveLength(1);
  expect(screen.getAllByRole("region", { name: "Error details" })).toHaveLength(2);
  view.rerender(<ErrorPopup message="prior_run_required" onDismiss={() => {}} />);
  expect(screen.getByRole("region", { name: "Error details" })).toBeInTheDocument();
  view.unmount(); expect(document.querySelector("#laomedo-error-popup-stack")).toBeNull();
});

jest.mock("@/components/ui/button", () => ({ Button: ({ size, ...props }: any) => <button {...props} /> }));
jest.mock("@/controllers/API/api", () => ({ api: { get: jest.fn(), post: jest.fn() } }));
jest.mock("@/customization/utils/urls", () => ({ getBaseUrl: () => "/api/v1/" }));

test("a native flow error preserves its message without an Agent cause",()=>{
 const {FlowErrorPopup}=require("./ErrorPopup");
 render(<FlowErrorPopup message="The expression cannot divide by zero." context={{}} laomedo={false} onDismiss={()=>{}}/>);
 expect(screen.getByRole("heading",{name:"Flow build failed"})).toBeVisible();
 expect(screen.getByText("The expression cannot divide by zero.")).toBeVisible();
 expect(document.body.textContent).not.toMatch(/runner|existing run|unrecognized_error/);
});
