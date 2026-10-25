import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import RecoveryPopup from "./RecoveryPopup";
import { api } from "@/controllers/API/api";

jest.mock("@/controllers/API/api", () => ({ api: { get: jest.fn(), post: jest.fn() } }));
jest.mock("@/customization/utils/urls", () => ({ getBaseUrl: () => "/api/v1/" }));
jest.mock("@/components/ui/button", () => ({ Button: ({ size, ...props }: any) => <button {...props} /> }));

beforeEach(() => {
  jest.clearAllMocks();
  (api.get as jest.Mock).mockResolvedValue({ data: { state: "offline", can_start: true } });
});

test("shows safe diagnostics, separate actions and only explicitly restarts the API", async () => {
  const dismissed = jest.fn();
  (api.post as jest.Mock).mockResolvedValue({ data: { state: "starting", can_start: false } });
  render(<RecoveryPopup message="runner_transport_failed; bearer private-payload" context={{ nodeLabel: "Claude Agent", operation: "status" }} onDismiss={dismissed} />);
  const restart = await screen.findByRole("button", { name: "Restart local backend" });
  expect(api.post).not.toHaveBeenCalled();
  expect(restart.parentElement?.tagName).toBe("FOOTER");
  expect(screen.getByText("Technical details").closest("details")).not.toHaveAttribute("open");
  expect(screen.queryByText(/private-payload/)).toBeNull();
  fireEvent.click(restart);
  await waitFor(() => expect(api.post).toHaveBeenCalledTimes(1));
  expect(screen.getByRole("button", { name: "Restarting..." })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "Dismiss" }));
  expect(dismissed).toHaveBeenCalledTimes(1);
});

test("Escape dismisses from inside the popup and restores prior focus on unmount", async () => {
  const trigger = document.createElement("button");
  document.body.append(trigger); trigger.focus();
  const dismissed = jest.fn();
  const view = render(<RecoveryPopup message="runner_transport_failed" context={{}} onDismiss={dismissed} />);
  const popup = await screen.findByRole("region", { name: "Local backend recovery" });
  expect(popup).toHaveFocus();
  fireEvent.keyDown(popup, { key: "Escape" });
  expect(dismissed).toHaveBeenCalledTimes(1);
  view.unmount();
  expect(trigger).toHaveFocus(); trigger.remove();
});

test("tracks visible viewport resize and scroll without canvas clipping", async () => {
  const viewport = Object.assign(new EventTarget(), { width: 360, height: 320, offsetLeft: 0, offsetTop: 80 });
  Object.defineProperty(window, "visualViewport", { configurable: true, value: viewport });
  const addListener = jest.spyOn(viewport, "addEventListener");
  const removeListener = jest.spyOn(viewport, "removeEventListener");
  const { unmount } = render(<RecoveryPopup message="runner_transport_failed" context={{}} onDismiss={jest.fn()} />);
  const popup = await screen.findByRole("region", { name: "Local backend recovery" });
  expect(popup.parentElement).toBe(document.body);
  expect(addListener).toHaveBeenCalledWith("resize", expect.any(Function));
  expect(addListener).toHaveBeenCalledWith("scroll", expect.any(Function));
  act(() => { viewport.height = 220; viewport.dispatchEvent(new Event("resize")); });
  // Actual CSS env()/min() viewport bounds are verified in the real browser; jsdom cannot parse them.
  act(() => { viewport.offsetTop = 120; viewport.dispatchEvent(new Event("scroll")); });
  expect(screen.getByRole("button", { name: "Dismiss" })).toBeVisible();
  unmount();
  expect(removeListener).toHaveBeenCalledWith("resize", expect.any(Function));
  expect(removeListener).toHaveBeenCalledWith("scroll", expect.any(Function));
  Object.defineProperty(window, "visualViewport", { configurable: true, value: undefined });
});

test("keeps errors visible until dismissed and never exposes a guessed restart", async () => {
  (api.get as jest.Mock).mockRejectedValue(new Error("unavailable"));
  render(<RecoveryPopup message="runner_transport_failed" context={{}} onDismiss={jest.fn()} />);
  await screen.findByRole("alert");
  expect(screen.queryByRole("button", { name: "Restart local backend" })).toBeNull();
  expect(screen.getByRole("button", { name: "Dismiss" })).toBeVisible();
  expect(api.post).not.toHaveBeenCalled();
});
