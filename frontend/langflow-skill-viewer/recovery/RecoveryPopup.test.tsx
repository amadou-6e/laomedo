import { act, configure, fireEvent, render, screen, waitFor } from "@testing-library/react";
import RecoveryPopup from "./RecoveryPopup";
import { api } from "@/controllers/API/api";

jest.mock("@/controllers/API/api", () => ({ api: { get: jest.fn(), post: jest.fn() } }));
jest.mock("@/customization/utils/urls", () => ({ getBaseUrl: () => "/api/v1/" }));
jest.mock("@/components/ui/button", () => ({ Button: ({ size, ...props }: any) => <button {...props} /> }));

configure({asyncUtilTimeout:5000});

beforeEach(() => {
  jest.resetAllMocks();
  (api.get as jest.Mock).mockResolvedValue({ data: { state: "offline", can_start: true } });
});

test("shows safe diagnostics, separate actions and only explicitly restarts the API", async () => {
  const dismissed = jest.fn();
  (api.post as jest.Mock).mockResolvedValueOnce({ data: { state: "starting", can_start: false, startup_id: "attempt-one" } }).mockResolvedValueOnce({data:{state:"offline",can_start:true,reason:"runner_start_cancelled"}});
  render(<RecoveryPopup message="runner_transport_failed; bearer private-payload" context={{ nodeLabel: "Claude Agent", operation: "status" }} onDismiss={dismissed} />);
  const restart = await screen.findByRole("button", { name: "Start local runner" });
  expect(api.post).not.toHaveBeenCalled();
  expect(restart.parentElement?.tagName).toBe("FOOTER");
  expect(screen.getByText("Technical details").closest("details")).not.toHaveAttribute("open");
  expect(screen.queryByText(/private-payload/)).toBeNull();
  fireEvent.click(restart);
  await waitFor(() => expect(api.post).toHaveBeenCalledTimes(1));
  expect(screen.getByRole("button", { name: "Starting..." })).toBeDisabled();
  expect(screen.getByRole("status")).toHaveAttribute("aria-busy", "true");
  expect(screen.queryByText(/Once reconnected/)).toBeNull();
  expect(screen.queryByText("Technical details")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
  await waitFor(() => expect(dismissed).toHaveBeenCalledTimes(1));
  expect(api.post).toHaveBeenLastCalledWith("/api/v1/laomedo/runner-service/cancel-start", null, {params:{startup_id:"attempt-one"},timeout:10000});
});

test("Docker down prompts the user instead of offering a runner start", async () => {
  (api.get as jest.Mock).mockResolvedValue({data:{state:"prerequisite",can_start:false,reason:"runner_docker_unavailable"}});
  render(<RecoveryPopup message="runner_transport_failed; SECRET" context={{nodeId:"agent",nodeLabel:"Claude Agent",operation:"status"}} onDismiss={jest.fn()} />);
  expect(await screen.findByRole("heading",{name:"Docker is not running"})).toBeVisible();
  expect(screen.getByText(/Start Docker Desktop/)).toBeVisible();
  expect(screen.getByText("The previous run's outcome is unconfirmed.")).toBeVisible();
  expect(screen.queryByRole("button",{name:"Start local runner"})).toBeNull();
  expect(screen.queryByRole("link",{name:/Install Docker/})).toBeNull();
  expect(screen.getByText(/"code": "runner_transport_failed"/)).toBeInTheDocument();
  expect(screen.getByText(/"recovery_code": "runner_docker_unavailable"/)).toBeInTheDocument();
  expect(screen.queryByText(/SECRET/)).toBeNull();
  expect(api.post).not.toHaveBeenCalled();
});

test("missing Docker offers only the fixed official external install action", async () => {
  (api.get as jest.Mock).mockResolvedValue({data:{state:"prerequisite",can_start:false,reason:"runner_docker_not_installed"}});
  render(<RecoveryPopup message="runner_transport_failed" context={{}} onDismiss={jest.fn()} />);
  const link=await screen.findByRole("link",{name:"Install Docker (opens in a new tab)"});
  expect(link).toHaveAttribute("href","https://docs.docker.com/get-started/get-docker/");
  expect(link).toHaveAttribute("rel","noopener noreferrer");
  expect(link.closest("footer")).not.toBeNull();
  expect(screen.queryByRole("button",{name:"Start local runner"})).toBeNull();
  expect(api.post).not.toHaveBeenCalled();
});

test("ambiguous Docker checks offer neither an install claim nor runner start", async () => {
  (api.get as jest.Mock).mockResolvedValue({data:{state:"prerequisite",can_start:false,reason:"runner_docker_check_unconfirmed"}});
  render(<RecoveryPopup message="runner_transport_failed" context={{}} onDismiss={jest.fn()} />);
  expect(await screen.findByRole("heading",{name:"Docker availability is unconfirmed"})).toBeVisible();
  expect(screen.queryByRole("link")).toBeNull();
  expect(screen.queryByRole("button",{name:"Start local runner"})).toBeNull();
});

test("healthy Docker and offline runner show the local start action", async () => {
  (api.get as jest.Mock).mockResolvedValue({data:{state:"offline",can_start:true,reason:"runner_local_offline"}});
  render(<RecoveryPopup message="runner_transport_failed" context={{}} onDismiss={jest.fn()} />);
  expect(await screen.findByRole("heading",{name:"Local runner is offline"})).toBeVisible();
  expect(screen.getByRole("button",{name:"Start local runner"})).toBeEnabled();
  expect(screen.queryByRole("link")).toBeNull();
  expect(api.post).not.toHaveBeenCalled();
});

test("online guidance is not repeated or conditional on a future reconnect", async () => {
  (api.get as jest.Mock).mockResolvedValue({data:{state:"ready",can_start:false}});
  render(<RecoveryPopup message="runner_transport_failed" context={{}} onDismiss={jest.fn()} />);
  expect(await screen.findByText("The local runner is online. Check the existing run before starting new work.")).toBeVisible();
  expect(screen.getByRole("region", {name:"Local backend recovery"})).toHaveStyle({borderLeftColor:"#4ADE80"});
  expect(screen.queryByText(/Once reconnected/)).toBeNull();
  expect(screen.queryByText(/Starting the runner does not rerun/)).toBeNull();
});

test("a healthy API does not turn an unresolved catalogue failure green", async () => {
  (api.get as jest.Mock).mockResolvedValue({data:{state:"ready",can_start:false}});
  render(<RecoveryPopup message="runner_model_catalog_unavailable_check_runner_connection" context={{nodeId:"agent"}} onDismiss={jest.fn()} />);
  await screen.findByText(/Open Model and use Refresh/);
  const popup=screen.getByRole("region",{name:"Local backend recovery"});
  expect(popup).toHaveStyle({borderLeftColor:"#F87171"});
  expect(popup).toHaveAttribute("data-error-code","runner_model_catalog_unavailable_check_runner_connection");
  expect(api.post).not.toHaveBeenCalled();
});

test("Escape dismisses from inside the popup and restores prior focus on unmount", async () => {
  const trigger = document.createElement("button");
  document.body.append(trigger); trigger.focus();
  const dismissed = jest.fn();
  const view = render(<RecoveryPopup message="runner_transport_failed" context={{}} onDismiss={dismissed} />);
  const popup = await screen.findByRole("region", { name: "Local backend recovery" });
  expect(popup).toHaveFocus();
  fireEvent.keyDown(popup, { key: "Escape" });
  await waitFor(() => expect(dismissed).toHaveBeenCalledTimes(1));
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
  expect(popup.parentElement?.id).toBe("laomedo-error-popup-stack");
  expect(addListener).toHaveBeenCalledWith("resize", expect.any(Function));
  expect(addListener).toHaveBeenCalledWith("scroll", expect.any(Function));
  act(() => { viewport.height = 220; viewport.dispatchEvent(new Event("resize")); });
  // Actual CSS env()/min() viewport bounds are verified in the real browser; jsdom cannot parse them.
  act(() => { viewport.offsetTop = 120; viewport.dispatchEvent(new Event("scroll")); });
  expect(await screen.findByRole("button", { name: "Dismiss" })).toBeVisible();
  unmount();
  expect(removeListener).toHaveBeenCalledWith("resize", expect.any(Function));
  expect(removeListener).toHaveBeenCalledWith("scroll", expect.any(Function));
  Object.defineProperty(window, "visualViewport", { configurable: true, value: undefined });
});

test("keeps errors visible until dismissed and never exposes a guessed restart", async () => {
  (api.get as jest.Mock).mockRejectedValue(new Error("unavailable"));
  render(<RecoveryPopup message="runner_transport_failed" context={{}} onDismiss={jest.fn()} />);
  await screen.findByRole("alert");
  expect(screen.queryByRole("button", { name: "Start local runner" })).toBeNull();
  expect(screen.getByRole("button", { name: "Dismiss" })).toBeVisible();
  expect(api.post).not.toHaveBeenCalled();
});


test("connection discovery shows activity without premature recovery advice or diagnostics", async () => {
 let resolve: (value: unknown) => void = () => {};
 (api.get as jest.Mock).mockImplementation(() => new Promise(done => { resolve = done; }));
 render(<RecoveryPopup message="runner_transport_failed" context={{}} onDismiss={jest.fn()} />);
 const status = screen.getByRole("status");
 expect(status).toHaveAttribute("aria-busy", "true");
 expect(status.querySelector("svg.animate-spin")).not.toBeNull();
 expect(screen.queryByText(/Once reconnected/)).toBeNull();
 expect(screen.queryByText("Technical details")).toBeNull();
 expect(screen.getByRole("button", { name: "Cancel" })).toBeEnabled();
 await act(async () => resolve({data:{state:"offline",can_start:true}}));
 expect(screen.getByRole("status")).toHaveAttribute("aria-busy", "false");
 expect(screen.getByText(/Starting the runner does not rerun/)).toBeVisible();
 expect(screen.getByText("Technical details")).toBeVisible();
});


test("unconfirmed cancellation ends the spinner and stays visible without operator advice", async () => {
 (api.post as jest.Mock).mockResolvedValueOnce({data:{state:"starting",can_start:false,startup_id:"attempt-one"}})
   .mockResolvedValueOnce({data:{state:"starting",can_start:false,startup_id:"attempt-one",reason:"runner_start_cancel_unconfirmed"}});
 render(<RecoveryPopup message="runner_transport_failed" context={{}} onDismiss={jest.fn()} />);
 fireEvent.click(await screen.findByRole("button",{name:"Start local runner"}));
 fireEvent.click(await screen.findByRole("button",{name:"Cancel",exact:true}));
 await screen.findByText("The local backend has not confirmed that startup stopped.");
 expect(screen.getByRole("status")).toHaveAttribute("aria-busy","false");
 expect(screen.queryByText(/operator/)).toBeNull();
 expect(screen.getByText("Technical details")).toBeVisible();
});


test("an unrelated startup crash is not presented as a successful cancel", async () => {
 const dismissed=jest.fn();
 (api.post as jest.Mock).mockResolvedValueOnce({data:{state:"starting",can_start:false,startup_id:"attempt-one"}})
  .mockResolvedValueOnce({data:{state:"offline",can_start:true,reason:"runner_start_failed"}});
 render(<RecoveryPopup message="runner_transport_failed" context={{}} onDismiss={dismissed} />);
 fireEvent.click(await screen.findByRole("button",{name:"Start local runner"}));
 fireEvent.click(await screen.findByRole("button",{name:"Cancel",exact:true}));
 await screen.findByText("The local backend has not confirmed that startup stopped.");
 expect(dismissed).not.toHaveBeenCalled();
 expect(screen.getByRole("button",{name:"Dismiss",exact:true})).toBeEnabled();
});


test("catalogue recovery waits for actual models and remains actionable after failure", async () => {
  (api.get as jest.Mock).mockResolvedValue({data:{state:"ready",can_start:false}});
  const dismissed=jest.fn(); const requested=jest.fn();
  window.addEventListener("laomedo-refresh-model-catalog",requested);
  render(<RecoveryPopup message="runner_model_catalog_unavailable_check_runner_connection" context={{nodeId:"agent"}} onDismiss={dismissed}/>);
  fireEvent.click(await screen.findByRole("button",{name:"Refresh models"}));
  expect(requested).toHaveBeenCalledTimes(1);
  expect(dismissed).not.toHaveBeenCalled();
  expect(screen.getByRole("button",{name:"Loading models..."})).toBeDisabled();
  act(()=>window.dispatchEvent(new CustomEvent("laomedo-model-catalog-loaded",{detail:{nodeId:"other"}})));
  expect(dismissed).not.toHaveBeenCalled();
  act(()=>window.dispatchEvent(new CustomEvent("laomedo-model-catalog-settled",{detail:{nodeId:"agent"}})));
  expect(screen.getByRole("button",{name:"Refresh models"})).toBeEnabled();
  expect(dismissed).not.toHaveBeenCalled();
  act(()=>window.dispatchEvent(new CustomEvent("laomedo-model-catalog-loaded",{detail:{nodeId:"agent"}})));
  expect(dismissed).toHaveBeenCalledTimes(1);
  expect(api.post).not.toHaveBeenCalled();
  window.removeEventListener("laomedo-refresh-model-catalog",requested);
});
