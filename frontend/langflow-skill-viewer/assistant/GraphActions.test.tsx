import { fireEvent, render, screen } from "@testing-library/react";
import GraphActions from "./GraphActions";
import { assistantRequest } from "./api";
import type { GraphAction } from "./models";
jest.mock("./api", () => ({ assistantRequest: jest.fn() }));
const action: GraphAction = {
  id: "action",
  message_id: "message",
  workflow_id: "graph",
  name: "Actual graph",
  kind: "edit",
  digest: "a".repeat(64),
  revision: "sha256:" + "b".repeat(64),
  preview: [
    "Set input: old -> new",
    "Reload open editor tabs before saving; unsaved editor work may overwrite this saved change.",
  ],
  state: "pending",
  expires_at: Date.now() / 1000 + 900,
  run_id: null,
};
describe("human graph approval", () => {
  beforeEach(() => jest.clearAllMocks());
  it("does nothing until a human approves the exact digest", async () => {
    jest
      .mocked(assistantRequest)
      .mockResolvedValue({ ...action, state: "succeeded" });
    render(
      <GraphActions
        conversation="chat"
        actions={[action]}
        onFailure={() => {}}
      />,
    );
    expect(assistantRequest).not.toHaveBeenCalled();
    expect(screen.getByText(/Reload open editor/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Approve changes" }));
    await screen.findByText("Saved graph updated.");
    expect(assistantRequest).toHaveBeenCalledWith(
      "/conversations/chat/actions/action/decision",
      { decision: "approve", digest: action.digest },
    );
    expect(
      screen.getByRole("link", { name: /Open graph/ }).getAttribute("target"),
    ).toBe("_blank");
    expect(
      screen.queryByRole("button", { name: "Approve changes" }),
    ).toBeNull();
  });
  it("rejects and retains the refusal instead of running", async () => {
    jest
      .mocked(assistantRequest)
      .mockResolvedValue({ ...action, state: "rejected" });
    render(
      <GraphActions
        conversation="chat"
        actions={[action]}
        onFailure={() => {}}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Reject" }));
    await screen.findByText("Rejected. No action was executed.");
    expect(assistantRequest).toHaveBeenCalledTimes(1);
  });
  it("never enables approval for expired or uncertain retained actions", () => {
    render(
      <GraphActions
        conversation="chat"
        actions={[
          { ...action, expires_at: 0 },
          { ...action, id: "uncertain", state: "unknown" },
        ]}
        onFailure={() => {}}
      />,
    );
    expect(screen.queryByRole("button")).toBeNull();
    expect(assistantRequest).not.toHaveBeenCalled();
    expect(screen.getByText(/Outcome uncertain/)).toBeTruthy();
  });
});
