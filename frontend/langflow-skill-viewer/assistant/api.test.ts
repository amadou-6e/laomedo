import { assistantRequest, AssistantFailure } from "./api";

jest.mock("@/stores/authStore", () => ({
  __esModule: true,
  default: { getState: () => ({ accessToken: "fixture-app-session" }) },
}));

describe("assistant request authority and uncertain dispatch", () => {
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
      headers: { Authorization: "Bearer fixture-app-session" },
    });
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
});
