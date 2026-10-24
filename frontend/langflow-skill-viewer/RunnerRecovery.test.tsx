import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import RunnerRecovery, { isRunnerConnectionError } from "./RunnerRecovery";
import { api } from "@/controllers/API/api";

jest.mock("@/controllers/API/api", () => ({ api: { get: jest.fn(), post: jest.fn() } }));
jest.mock("@/customization/utils/urls", () => ({ getBaseUrl: () => "/api/v1/" }));
jest.mock("@/components/ui/button", () => ({ Button: ({ size, ...props }: any) => <button {...props} /> }));
const endpoint = "/api/v1/laomedo/runner-service";
const failure = "Error building Component Laomedo Claude Agent:\n\nrunner_transport_failed";
beforeEach(() => { jest.resetAllMocks(); });

test("unrelated errors do not create recovery controls or query a runner", () => {
  render(<RunnerRecovery message="task_required" />);
  expect(api.get).not.toHaveBeenCalled();
  expect(screen.queryByRole("region")).toBeNull();
  expect(isRunnerConnectionError("not_runner_transport_failed_suffix")).toBe(false);
  expect(isRunnerConnectionError("Task text mentions runner_transport_failed but another operation failed")).toBe(false);
});

test("the error UI restarts the host-configured API without a graph URL or dispatch", async () => {
  (api.get as jest.Mock).mockResolvedValue({ data: { state: "offline", can_start: true } });
  let finish: (value: unknown) => void = () => {};
  (api.post as jest.Mock).mockImplementation(() => new Promise(resolve => { finish = resolve; }));
  render(<RunnerRecovery message={failure} />);
  const button = await screen.findByRole("button", { name: "Restart local backend" });
  fireEvent.click(button); fireEvent.click(button);
  expect(api.post).toHaveBeenCalledTimes(1);
  expect(api.post).toHaveBeenCalledWith(`${endpoint}/start`, null);
  expect(api.get).toHaveBeenCalledWith(endpoint, { signal: expect.any(AbortSignal) });
  expect(screen.getByRole("button", { name: "Restarting local backend..." })).toBeDisabled();
  await act(async () => finish({ data: { state: "starting", can_start: false } }));
  expect(screen.getByText(/does not rerun the graph/)).toBeVisible();
});

test("unconfigured or unidentified services cannot be started", async () => {
  (api.get as jest.Mock).mockResolvedValue({ data: { state: "unmanaged", can_start: false } });
  render(<RunnerRecovery message={failure} />);
  await screen.findByText(/recovery is not configured/);
  expect(screen.queryByRole("button")).toBeNull();
  expect(api.post).not.toHaveBeenCalled();
});

test("failed startup keeps an explicit API-only recovery action", async () => {
  (api.get as jest.Mock).mockResolvedValue({ data: { state: "offline", can_start: true } });
  (api.post as jest.Mock).mockRejectedValue(new Error("private transport details"));
  render(<RunnerRecovery message={failure} />);
  fireEvent.click(await screen.findByRole("button", { name: "Restart local backend" }));
  await screen.findByRole("alert");
  expect(screen.getByRole("button", { name: "Restart local backend" })).toBeEnabled();
  expect(screen.queryByText(/private transport details/)).toBeNull();
  expect(api.post).toHaveBeenCalledTimes(1);
});

test("availability failures do not guess that a backend can safely be restarted", async () => {
  (api.get as jest.Mock).mockRejectedValue(new Error("unauthorized"));
  render(<RunnerRecovery message={failure} />);
  await screen.findByRole("alert");
  expect(screen.queryByRole("button")).toBeNull();
});

test("polling reports readiness without promoting historical verification limits into runtime state", async () => {
  jest.useFakeTimers();
  try {
    (api.get as jest.Mock).mockResolvedValueOnce({ data: { state: "offline", can_start: true } })
      .mockResolvedValue({ data: { state: "ready", can_start: false } });
    (api.post as jest.Mock).mockResolvedValue({ data: { state: "starting", can_start: false } });
    render(<RunnerRecovery message={failure} />);
    fireEvent.click(await screen.findByRole("button", { name: "Restart local backend" }));
    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(1));
    await act(async () => { await jest.advanceTimersByTimeAsync(2000); });
    await screen.findByText(/local runner backend is online/);
    expect(screen.queryByRole("button")).toBeNull();
    expect(api.post).toHaveBeenCalledTimes(1);
  } finally { jest.useRealTimers(); }
});

test("a stale pre-click availability response cannot undo the starting state", async () => {
 jest.useFakeTimers();
 try {
  let oldPoll: (value: unknown) => void = () => {};
  (api.get as jest.Mock).mockResolvedValueOnce({data:{state:"offline",can_start:true}})
   .mockImplementationOnce(() => new Promise(resolve => { oldPoll = resolve; }))
   .mockResolvedValue({data:{state:"ready",can_start:false}});
  (api.post as jest.Mock).mockResolvedValue({data:{state:"starting",can_start:false}});
  render(<RunnerRecovery message={failure}/>);
  const button=await screen.findByRole("button",{name:"Restart local backend"});
  await act(async()=>{await jest.advanceTimersByTimeAsync(2000)});
  fireEvent.click(button);
  await screen.findByRole("button",{name:"Restarting local backend..."});
  await act(async()=>oldPoll({data:{state:"offline",can_start:true}}));
  expect(screen.getByRole("button",{name:"Restarting local backend..."})).toBeDisabled();
  await act(async()=>{await jest.advanceTimersByTimeAsync(2000)});
  await screen.findByText(/local runner backend is online/);
  expect(api.post).toHaveBeenCalledTimes(1);
 } finally {jest.useRealTimers()}
});

test("a process that exits during startup explains the failure rather than just saying offline", async () => {
 (api.get as jest.Mock).mockResolvedValue({data:{state:"offline",can_start:true,reason:"runner_start_failed"}});
 render(<RunnerRecovery message={failure}/>);
 await screen.findByText(/exited; readiness could not be confirmed.*host startup log/);
 expect(screen.getByRole("button",{name:"Restart local backend"})).toBeEnabled();
});

test("a failed later poll removes stale permission to restart", async () => {
 jest.useFakeTimers();
 try {
  (api.get as jest.Mock).mockResolvedValueOnce({data:{state:"offline",can_start:true}}).mockRejectedValue(new Error("connection"));
  render(<RunnerRecovery message={failure}/>);
  await screen.findByRole("button",{name:"Restart local backend"});
  await act(async()=>{await jest.advanceTimersByTimeAsync(2000)});
  await screen.findByRole("alert");
  expect(screen.queryByRole("button")).toBeNull();
 } finally {jest.useRealTimers()}
});
