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

test("native model discovery failure offers managed startup without dispatch", async () => {
  (api.get as jest.Mock).mockResolvedValue({data:{state:"offline",can_start:true}});
  render(<RunnerRecovery message="runner_model_catalog_unavailable_check_runner_connection" />);
  await screen.findByRole("button",{name:"Start local runner"});
  expect(screen.getByText(/Starting the runner does not submit an agent task/)).toBeVisible();
  expect(api.post).not.toHaveBeenCalled();
  expect(isRunnerConnectionError("Task mentions runner_model_catalog_unavailable_check_runner_connection")).toBe(false);
});

test("model discovery failure on a ready backend offers refresh without restart", async () => {
  (api.get as jest.Mock).mockResolvedValue({data:{state:"ready",can_start:false}});
  render(<RunnerRecovery message="runner_model_catalog_unavailable_check_runner_connection" />);
  await screen.findByText(/Open Model and use Refresh/);
  expect(screen.queryByRole("button")).toBeNull();
  expect(api.post).not.toHaveBeenCalled();
});

test("the error UI restarts the host-configured API without a graph URL or dispatch", async () => {
  (api.get as jest.Mock).mockResolvedValue({ data: { state: "offline", can_start: true } });
  let finish: (value: unknown) => void = () => {};
  (api.post as jest.Mock).mockImplementation(() => new Promise(resolve => { finish = resolve; }));
  render(<RunnerRecovery message={failure} />);
  const button = await screen.findByRole("button", { name: "Start local runner" });
  fireEvent.click(button); fireEvent.click(button);
  expect(api.post).toHaveBeenCalledTimes(1);
  expect(api.post).toHaveBeenCalledWith(`${endpoint}/start`, null, {timeout:10000});
  expect(api.get).toHaveBeenCalledWith(endpoint, { signal: expect.any(AbortSignal), timeout:10000 });
  expect(screen.getByRole("button", { name: "Starting local runner..." })).toBeDisabled();
  await act(async () => finish({ data: { state: "starting", can_start: false } }));
  expect(screen.queryByText(/does not rerun the graph/)).toBeNull();
});

test("unconfigured or unidentified services cannot be started", async () => {
  (api.get as jest.Mock).mockResolvedValue({ data: { state: "unmanaged", can_start: false } });
  render(<RunnerRecovery message={failure} />);
  await screen.findByText(/recovery is not configured/);
  expect(screen.queryByRole("button")).toBeNull();
  expect(api.post).not.toHaveBeenCalled();
});

test("failed startup waits for a fresh offline status before offering recovery", async () => {
  (api.get as jest.Mock).mockResolvedValue({ data: { state: "offline", can_start: true } });
  (api.post as jest.Mock).mockRejectedValue(new Error("private transport details"));
  render(<RunnerRecovery message={failure} />);
  fireEvent.click(await screen.findByRole("button", { name: "Start local runner" }));
  await screen.findByRole("alert");
  expect(screen.queryByRole("button", { name: "Start local runner" })).toBeNull();
  expect(await screen.findByRole("button", { name: "Start local runner" }, {timeout:5000})).toBeEnabled();
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
    fireEvent.click(await screen.findByRole("button", { name: "Start local runner" }));
    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(1));
    await act(async () => { await jest.advanceTimersByTimeAsync(2000); });
    await screen.findByText(/local runner is online/);
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
  const button=await screen.findByRole("button",{name:"Start local runner"});
  await act(async()=>{await jest.advanceTimersByTimeAsync(2000)});
  fireEvent.click(button);
  await screen.findByRole("button",{name:"Starting local runner..."});
  await act(async()=>oldPoll({data:{state:"offline",can_start:true}}));
  expect(screen.getByRole("button",{name:"Starting local runner..."})).toBeDisabled();
  await act(async()=>{await jest.advanceTimersByTimeAsync(2000)});
  await screen.findByText(/local runner is online/);
  expect(api.post).toHaveBeenCalledTimes(1);
 } finally {jest.useRealTimers()}
});

test("a process that exits during startup explains the failure rather than just saying offline", async () => {
 (api.get as jest.Mock).mockResolvedValue({data:{state:"offline",can_start:true,reason:"runner_start_failed"}});
 render(<RunnerRecovery message={failure}/>);
 await screen.findByText("The local runner exited before it was ready.");
 expect(screen.queryByText(/operator|startup log/i)).toBeNull();
 expect(screen.getByRole("button",{name:"Start local runner"})).toBeEnabled();
});

test("a failed later poll removes stale permission to restart", async () => {
 jest.useFakeTimers();
 try {
  (api.get as jest.Mock).mockResolvedValueOnce({data:{state:"offline",can_start:true}}).mockRejectedValue(new Error("connection"));
  render(<RunnerRecovery message={failure}/>);
  await screen.findByRole("button",{name:"Start local runner"});
  await act(async()=>{await jest.advanceTimersByTimeAsync(2000)});
  await screen.findByRole("alert");
  expect(screen.queryByRole("button")).toBeNull();
 } finally {jest.useRealTimers()}
});


test("a timed-out restart clears the spinner and resumes status checking", async () => {
 (api.get as jest.Mock).mockResolvedValue({data:{state:"offline",can_start:true}});
 (api.post as jest.Mock).mockRejectedValue(new Error("timeout"));
 render(<RunnerRecovery message={failure}/>);
 fireEvent.click(await screen.findByRole("button",{name:"Start local runner"}));
 await screen.findByText("The local runner startup could not be confirmed.");
 expect(screen.queryByRole("button",{name:"Starting local runner..."})).toBeNull();
 expect(api.post).toHaveBeenCalledWith(`${endpoint}/start`,null,{timeout:10000});
});


test("a client promise that never settles cannot keep restarting forever", async () => {
 jest.useFakeTimers();
 try {
  (api.get as jest.Mock).mockResolvedValue({data:{state:"offline",can_start:true}});
  (api.post as jest.Mock).mockImplementation(() => new Promise(() => {}));
  render(<RunnerRecovery message={failure}/>);
  fireEvent.click(await screen.findByRole("button",{name:"Start local runner"}));
  expect(screen.getByRole("button",{name:"Starting local runner..."})).toBeDisabled();
  await act(async()=>{await jest.advanceTimersByTimeAsync(10000)});
  expect(screen.queryByRole("button",{name:"Starting local runner..."})).toBeNull();
  expect(screen.getByRole("alert")).toHaveTextContent("startup could not be confirmed");
 } finally {jest.useRealTimers()}
});
