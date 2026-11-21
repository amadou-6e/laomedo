import { fireEvent, render, screen } from "@testing-library/react";
import NativeActions from "./NativeActions";
import { assistantRequest } from "./api";
import type { NativeAction } from "./models";
jest.mock("./api", () => ({ assistantRequest: jest.fn() }));
const action: NativeAction = { id: "proposal", message_id: "message", name: "review",
  arguments: "inspect error handling", digest: "a".repeat(64), state: "pending",
  may_use_model: true, can_decide: true, result_message_id: null };

beforeEach(() => jest.clearAllMocks());

test("shows exact native arguments and submits nothing before human approval", async () => {
  jest.mocked(assistantRequest).mockResolvedValue({ ...action, state: "executing", can_decide: false });
  render(<NativeActions conversation="chat" actions={[action]} onFailure={() => {}} />);
  expect(screen.getByText('Run /review with arguments "inspect error handling".')).toBeVisible();
  expect(screen.getByText(/May use model quota/)).toBeVisible();
  expect(assistantRequest).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Approve" }));
  await screen.findByText("Running");
  expect(assistantRequest).toHaveBeenCalledWith("/conversations/chat/native-actions/proposal/decision", { decision: "approve", digest: action.digest });
  expect(screen.queryByRole("button", { name: "Approve" })).toBeNull();
});

test("completed, rejected and foreign-session receipts offer no execution control", () => {
  render(<NativeActions conversation="chat" actions={[
    { ...action, state: "completed" },
    { ...action, id: "rejected", state: "rejected" },
    { ...action, id: "foreign", can_decide: false },
  ]} onFailure={() => {}} />);
  expect(screen.getByText('Ran /review with arguments "inspect error handling".')).toBeVisible();
  expect(screen.getByText("Completed")).toBeVisible();
  expect(screen.getByText("Rejected")).toBeVisible();
  expect(screen.queryByRole("button")).toBeNull();
  expect(assistantRequest).not.toHaveBeenCalled();
});
test("labels a received Claude control report neutrally even if it describes a native error", () => {
  render(<NativeActions conversation="chat" provider="claude" actions={[{...action, name: "usage", arguments: "", may_use_model: false, state: "completed"}]} onFailure={() => {}} />);
  expect(screen.getByText("Received output from /usage.")).toBeVisible();
  expect(screen.getByText("Output received")).toBeVisible();
  expect(screen.queryByText("Completed")).toBeNull();
});
