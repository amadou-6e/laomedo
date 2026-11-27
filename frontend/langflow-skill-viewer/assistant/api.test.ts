import { assistantRequest, AssistantFailure, lockAssistant } from "./api";

jest.mock("@/stores/authStore", () => ({
  __esModule: true,
  default: { getState: () => ({ accessToken: "fixture-app-session" }) },
}));

describe("assistant request authority and uncertain dispatch", () => {
  it("never blocks upstream logout when chat is unavailable", async () => {
    jest
      .spyOn(globalThis, "fetch")
      .mockRejectedValue(new TypeError("unavailable"));
    await expect(lockAssistant()).resolves.toBeUndefined();
  });
  const originalFetch = globalThis.fetch;
  beforeAll(() => {
    globalThis.fetch = jest.fn();
  });
  beforeEach(() => jest.clearAllMocks());
  afterAll(() => {
    globalThis.fetch = originalFetch;
  });
  afterEach(() => jest.restoreAllMocks());

  it("submits a mutation once and never retries a lost acknowledgement", async () => {
    const fetcher = jest
      .spyOn(globalThis, "fetch")
      .mockRejectedValue(new TypeError("private transport detail"));
    await expect(
      assistantRequest("/conversations/id/messages", {
        client_message_id: "same-key",
        text: "Hello",
      }),
    ).rejects.toEqual(new AssistantFailure("assistant_dispatch_unknown"));
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(fetcher.mock.calls[0][1]).toMatchObject({
      method: "POST",
      credentials: "same-origin",
      cache: "no-store",
      headers: { "Content-Type": "application/json" },
    });
    expect(fetcher.mock.calls[0][1]?.headers).not.toHaveProperty("Authorization");
  });

  it("locks on expired authority without attempting authentication refresh", async () => {
    const fetcher = jest.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: false,
      status: 403,
      json: async () => ({ detail: "PRIVATE_CANARY" }),
    } as Response);
    await expect(assistantRequest("/conversations")).rejects.toEqual(
      new AssistantFailure("assistant_session_locked"),
    );
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it("does not display arbitrary server error text", async () => {
    jest.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: false,
      status: 500,
      json: async () => ({ detail: { code: "PRIVATE secret text" } }),
    } as Response);
    await expect(assistantRequest("/conversations")).rejects.toEqual(
      new AssistantFailure("assistant_connection_unavailable"),
    );
  });
  it("allows a slow native model discovery to finish without retrying", async () => {
    jest.useFakeTimers();
    try {
      let signal: AbortSignal;
      let finish: (value: Response) => void;
      const fetcher = jest.spyOn(globalThis, "fetch").mockImplementation((_url, options) => {
        signal = options!.signal as AbortSignal;
        return new Promise<Response>((resolve) => { finish = resolve; });
      });
      const pending = assistantRequest("/models?provider=codex&connection_generation=2");
      await jest.advanceTimersByTimeAsync(55000);
      expect(signal!.aborted).toBe(false);
      finish!({ ok: true, json: async () => ({ models: [] }) } as Response);
      await expect(pending).resolves.toEqual({ models: [] });
      expect(fetcher).toHaveBeenCalledTimes(1);
      expect(jest.getTimerCount()).toBe(0);
    } finally {
      jest.useRealTimers();
    }
  });

  it("bounds model discovery and preserves the shorter deadline for other reads", async () => {
    jest.useFakeTimers();
    try {
      const signals: AbortSignal[] = [];
      jest.spyOn(globalThis, "fetch").mockImplementation((_url, options) => {
        const signal = options!.signal as AbortSignal;
        signals.push(signal);
        return new Promise<Response>((_resolve, reject) => {
          signal.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")));
        });
      });
      const models = assistantRequest("/models?provider=codex").catch((error) => error);
      const ordinary = assistantRequest("/conversations").catch((error) => error);
      await jest.advanceTimersByTimeAsync(20000);
      expect(signals[0].aborted).toBe(false);
      expect(signals[1].aborted).toBe(true);
      expect(await ordinary).toEqual(new AssistantFailure("assistant_connection_unavailable"));
      await jest.advanceTimersByTimeAsync(70000);
      expect(signals[0].aborted).toBe(true);
      expect(await models).toEqual(new AssistantFailure("assistant_connection_unavailable"));
    } finally {
      jest.useRealTimers();
    }
  });

});
