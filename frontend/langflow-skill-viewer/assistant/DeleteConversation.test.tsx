import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import DeleteConversation from "./DeleteConversation";
import { AssistantFailure, assistantRequest } from "./api";
jest.mock("./api", () => ({ ...jest.requireActual("./api"), assistantRequest: jest.fn() }));

const props = { conversation: "chat", title: "My conversation", onDeleted: jest.fn(), onFailure: jest.fn() };
beforeEach(() => { jest.clearAllMocks(); });

it("names the chat and deletes only after explicit confirmation; Cancel preserves it", async () => {
  jest.mocked(assistantRequest).mockResolvedValue({ state: "deleted" });
  render(<DeleteConversation {...props} />);
  fireEvent.click(screen.getByRole("button", { name: "Delete conversation" }));
  expect(screen.getByRole("dialog").textContent).toContain("My conversation");
  expect(screen.getByRole("dialog").textContent).toContain("from Laomedo history");
  expect(screen.getByRole("dialog").textContent).toContain("Saved workflows will stay");
  expect(assistantRequest).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
  expect(assistantRequest).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Delete conversation" }));
  fireEvent.click(screen.getByRole("button", { name: "Delete", exact: true }));
  await waitFor(() => expect(props.onDeleted).toHaveBeenCalledTimes(1));
  expect(assistantRequest).toHaveBeenCalledWith("/conversations/chat", undefined, expect.any(AbortSignal), "DELETE");
});

it("keeps the chat on an active-work refusal and never retries automatically", async () => {
  jest.mocked(assistantRequest).mockRejectedValue(new AssistantFailure("assistant_conversation_active"));
  render(<DeleteConversation {...props} />);
  fireEvent.click(screen.getByRole("button", { name: "Delete conversation" }));
  fireEvent.click(screen.getByRole("button", { name: "Delete", exact: true }));
  await screen.findByRole("alert");
  expect(screen.getByRole("alert").textContent).toContain("active response or workflow run");
  expect(props.onDeleted).not.toHaveBeenCalled();
  expect(assistantRequest).toHaveBeenCalledTimes(1);
});

it("discards a late result after changing owner/conversation unmounts the control", async () => {
  let finish!: (value: unknown) => void;
  jest.mocked(assistantRequest).mockReturnValue(new Promise((resolve) => { finish = resolve; }));
  const view = render(<DeleteConversation {...props} />);
  fireEvent.click(screen.getByRole("button", { name: "Delete conversation" }));
  fireEvent.click(screen.getByRole("button", { name: "Delete", exact: true }));
  const signal = jest.mocked(assistantRequest).mock.calls[0][2];
  view.unmount();
  expect(signal?.aborted).toBe(true);
  finish({ state: "deleted" });
  await Promise.resolve();
  expect(props.onDeleted).not.toHaveBeenCalled();
});
