import { privateSkillRequest } from "./api";

const selection = { connectionId: "connection", repositoryId: 123 };
const originalFetch = globalThis.fetch;

beforeEach(() => {
  Object.defineProperty(globalThis, "fetch", { configurable: true, writable: true, value: jest.fn() });
});

afterEach(() => {
  jest.restoreAllMocks();
  jest.useRealTimers();
  Object.defineProperty(globalThis, "fetch", { configurable: true, writable: true, value: originalFetch });
});

test("private requests work without AbortSignal.any and preserve caller cancellation", async () => {
  const originalAny = AbortSignal.any;
  Object.defineProperty(AbortSignal, "any", { configurable: true, value: undefined });
  const caller = new AbortController();
  const request = jest.spyOn(globalThis, "fetch").mockImplementation(async (_url, options) => {
    const signal = options?.signal as AbortSignal;
    caller.abort();
    expect(signal.aborted).toBe(true);
    throw new Error("aborted");
  });
  try {
    await expect(privateSkillRequest("discover", selection, {}, caller.signal)).rejects.toMatchObject({
      code: "github_connection_unavailable",
    });
    expect(request).toHaveBeenCalledTimes(1);
  } finally {
    Object.defineProperty(AbortSignal, "any", { configurable: true, value: originalAny });
  }
});

test("private requests remain bounded when no caller signal is provided", async () => {
  jest.useFakeTimers();
  const request = jest.spyOn(globalThis, "fetch").mockImplementation((_url, options) =>
    new Promise((_resolve, reject) => {
      (options?.signal as AbortSignal).addEventListener("abort", () => reject(new Error("timeout")));
    }),
  );
  const pending = privateSkillRequest("discover", selection);
  const rejection = expect(pending).rejects.toMatchObject({ code: "github_connection_unavailable" });
  await jest.advanceTimersByTimeAsync(120000);
  await rejection;
  expect(request).toHaveBeenCalledTimes(1);
});

test("the deadline and caller cancellation remain active while the response body is read", async () => {
  for (const cancelByCaller of [false, true]) {
    jest.useFakeTimers();
    const caller = new AbortController();
    const request = jest.spyOn(globalThis, "fetch").mockImplementation(async (_url, options) => {
      const signal = options?.signal as AbortSignal;
      return { json: () => new Promise((_resolve, reject) => {
        signal.addEventListener("abort", () => reject(new Error("aborted")));
      }) } as Response;
    });
    const pending = privateSkillRequest("discover", selection, {}, caller.signal);
    const rejection = expect(pending).rejects.toMatchObject({ code: "github_connection_unavailable" });
    await Promise.resolve();
    if (cancelByCaller) caller.abort();
    else await jest.advanceTimersByTimeAsync(120000);
    await rejection;
    expect(request).toHaveBeenCalledTimes(1);
    request.mockRestore();
    jest.useRealTimers();
  }
});
