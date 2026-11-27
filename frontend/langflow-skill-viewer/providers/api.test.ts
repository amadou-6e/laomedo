import { readSubscriptionLimits } from "./api";

const connection = "00000000-0000-4000-8000-000000000001";
const observation = {
  connection_id: connection,
  generation: 1,
  state: "ready",
  reason: null,
  observed_at: 1800000000,
  stale_after: 1800000060,
  snapshot: {
    submitted_turns: 0,
    buckets: [{
      limit_id: "opencode-go", label: "OpenCode Go", plan: null, credits: null,
      windows: [
        { kind: "primary", window_minutes: 300, used_percent: 30, resets_at: 1800000300 },
        { kind: "secondary", window_minutes: 10080, used_percent: 100, resets_at: 1800000600 },
        { kind: "monthly", window_minutes: null, used_percent: 50, resets_at: 1800000900 },
      ],
    }],
  },
};

beforeEach(() => {
  global.fetch = jest.fn().mockResolvedValue({ ok: true, json: async () => observation });
});
afterEach(() => jest.restoreAllMocks());

test("the real wire parser preserves all three Go meters", async () => {
  const result = await readSubscriptionLimits("graph-one", connection, 1, { refresh: true });
  expect(result.snapshot?.buckets[0].windows.map(window => window.kind)).toEqual(["primary", "secondary", "monthly"]);
  expect(result.snapshot?.buckets[0].windows[2].window_minutes).toBeNull();
  expect(global.fetch).toHaveBeenCalledWith(expect.stringContaining(`/limits/${connection}`), expect.objectContaining({ method: "POST", credentials: "same-origin", body: '{"generation":1}' }));
});

test.each(["authentication_failed", "not_entitled", "rate_limited"])("safe Go %s reason crosses the wire unchanged", async reason => {
  (global.fetch as jest.Mock).mockResolvedValue({ ok: true, json: async () => ({ ...observation, state: "unavailable", reason, snapshot: null }) });
  expect((await readSubscriptionLimits("graph-one", connection, 1)).reason).toBe(reason);
});

test("an oversized meter list is refused rather than silently dropping monthly data", async () => {
  const bucket = observation.snapshot.buckets[0];
  (global.fetch as jest.Mock).mockResolvedValue({ ok: true, json: async () => ({ ...observation, snapshot: { submitted_turns: 0, buckets: [{ ...bucket, windows: [...bucket.windows, bucket.windows[0]] }] } }) });
  await expect(readSubscriptionLimits("graph-one", connection, 1)).rejects.toThrow();
});
