import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import type { ReactElement } from "react";
import GraphActions from "./GraphActions";
import { assistantRequest } from "../api";
import type { GraphAction } from "../models";
jest.mock("../api", () => ({ assistantRequest: jest.fn() }));
const action: GraphAction = {
  id: "action",
  message_id: "message",
  workflow_id: "graph",
  name: "Actual graph",
  kind: "edit",
  category: "edit",
  summary: "Change the input text from old to new.",
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
function renderGraphActions(element: ReactElement) { return render(<MemoryRouter>{element}</MemoryRouter>); }
describe("human graph approval", () => {
  beforeEach(() => jest.clearAllMocks());
  it("does nothing until a human approves the exact digest", async () => {
    jest
      .mocked(assistantRequest)
      .mockResolvedValue({ ...action, state: "succeeded" });
    renderGraphActions(
      <GraphActions
        conversation="chat"
        actions={[action]}
        onFailure={() => {}}
      />,
    );
    expect(assistantRequest).not.toHaveBeenCalled();
    expect(
      screen.getByRole("heading", {
        name: 'Edit workflow "Actual graph": Change the input text from old to new.',
      }),
    ).toBeTruthy();
    expect(screen.queryByText("Edit workflow")).toBeNull();
    expect(
      screen.queryByText("Change the input text from old to new."),
    ).toBeNull();
    expect(screen.queryByText("Details")).toBeNull();
    expect(screen.queryByText(/Saved revision/)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));
    await screen.findByText("Edited");
    expect(assistantRequest).toHaveBeenCalledWith(
      "/conversations/chat/actions/action/decision",
      { decision: "approve", digest: action.digest },
    );
    expect(
      screen
        .getByRole("link", { name: "Open workflow" })
        .getAttribute("target"),
    ).toBeNull();
    expect(screen.queryByRole("button", { name: "Approve" })).toBeNull();
  });
  it("names the rename operation and shows its exact target without identifiers", () => {
    renderGraphActions(
      <GraphActions
        conversation="chat"
        actions={[
          {
            ...action,
            category: "rename",
            new_name: "New name",
            summary: "Redundant prose",
          },
        ]}
        onFailure={() => {}}
      />,
    );
    expect(
      screen.getByRole("heading", {
        name: 'Rename workflow "Actual graph" to "New name".',
      }),
    ).toBeTruthy();
    expect(
      screen.getByRole("article", { name: "Rename workflow: Actual graph" }),
    ).toBeTruthy();
    expect(screen.queryByText("Rename workflow")).toBeNull();
    expect(screen.queryByText("Redundant prose")).toBeNull();
    expect(screen.queryByText("Details")).toBeNull();
    expect(screen.queryByText(/Saved revision/)).toBeNull();
    expect(screen.getByRole("button", { name: "Approve" })).toBeTruthy();
  });
  it("grants the named category only after the human clicks Always approve", async () => {
    jest
      .mocked(assistantRequest)
      .mockResolvedValue({ ...action, state: "succeeded" });
    renderGraphActions(
      <GraphActions
        conversation="chat"
        actions={[action]}
        onFailure={() => {}}
      />,
    );
    expect(assistantRequest).not.toHaveBeenCalled();
    fireEvent.click(
      screen.getByRole("button", { name: "Always approve edits" }),
    );
    await screen.findByText("Edited");
    expect(assistantRequest).toHaveBeenCalledWith(
      "/conversations/chat/actions/action/decision",
      {
        decision: "always_approve",
        digest: action.digest,
      },
    );
  });
  it("describes a completed run with its actual input and places its outcome below", () => {
    renderGraphActions(
      <GraphActions
        conversation="chat"
        actions={[
          {
            ...action,
            kind: "run",
            category: "run",
            state: "succeeded",
            summary: "Run with input incorrect-summary",
            preview: [
              "Input: compact-auto-input",
              "Input type: chat",
              "Output type: any",
            ],
          },
        ]}
        onFailure={() => {}}
      />,
    );
    expect(
      screen.getByRole("heading", {
        name: 'Ran workflow "Actual graph" with input "compact-auto-input".',
      }),
    ).toBeTruthy();
    expect(screen.queryByText(/incorrect-summary/)).toBeNull();
    const outcome = screen.getByRole("status");
    expect(outcome.textContent).toBe("Completed");
    expect(outcome.className).toContain("text-left");
    expect(outcome.className).toContain("block");
    expect(outcome.parentElement?.contains(screen.getByRole("link"))).toBe(
      false,
    );
  });
  it("keeps empty input explicit and never calls a pending run completed", () => {
    renderGraphActions(
      <GraphActions
        conversation="chat"
        actions={[
          {
            ...action,
            kind: "run",
            category: "run",
            preview: ["Input: "],
          },
        ]}
        onFailure={() => {}}
      />,
    );
    expect(
      screen.getByRole("heading", {
        name: 'Run workflow "Actual graph" with input "".',
      }),
    ).toBeTruthy();
    expect(screen.queryByText("Completed")).toBeNull();
    expect(assistantRequest).not.toHaveBeenCalled();
  });
  it("rejects and retains the refusal instead of running", async () => {
    jest
      .mocked(assistantRequest)
      .mockResolvedValue({ ...action, state: "rejected" });
    renderGraphActions(
      <GraphActions
        conversation="chat"
        actions={[action]}
        onFailure={() => {}}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Reject" }));
    await screen.findByText("Rejected");
    expect(assistantRequest).toHaveBeenCalledTimes(1);
  });
  it("does not offer a decision from a different app session", () => {
    renderGraphActions(
      <GraphActions
        conversation="chat"
        actions={[{ ...action, can_decide: false }]}
        onFailure={() => {}}
      />,
    );
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.getByText("Another app session")).toBeTruthy();
    expect(assistantRequest).not.toHaveBeenCalled();
  });
  it("never enables approval for expired or uncertain retained actions", () => {
    renderGraphActions(
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
    expect(screen.getByText("Outcome unknown")).toBeTruthy();
  });
});


it("workflow link opens its graph through the current router without submitting a decision",()=>{
 jest.clearAllMocks();
 render(<MemoryRouter initialEntries={["/assistant"]}><Routes>
  <Route path="/assistant" element={<GraphActions conversation="chat" actions={[{...action,state:"succeeded"}]} onFailure={()=>{}}/>}/>
  <Route path="/flow/graph" element={<p>Workflow editor</p>}/>
 </Routes></MemoryRouter>);
 const link=screen.getByRole("link",{name:"Open workflow"});
 expect(link).toHaveAttribute("href","/flow/graph");
 expect(link).not.toHaveAttribute("target");
 fireEvent.click(link);
 expect(screen.getByText("Workflow editor")).toBeVisible();
 expect(assistantRequest).not.toHaveBeenCalled();
});

it("uses document navigation to reload an already open graph through its beforeunload guard", () => {
  jest.clearAllMocks();
  render(<MemoryRouter initialEntries={["/flow/graph"]}>
    <GraphActions conversation="chat" actions={[{ ...action, state: "succeeded" }]} onFailure={() => {}} />
  </MemoryRouter>);
  const link = screen.getByRole("link", { name: "Open workflow" });
  // Router navigation cancels the native event; reloadDocument leaves it to the
  // browser, which invokes FlowPage's existing unsaved/build beforeunload guard.
  expect(fireEvent.click(link)).toBe(true);
  expect(link).toHaveAttribute("href", "/flow/graph");
  expect(assistantRequest).not.toHaveBeenCalled();
});
