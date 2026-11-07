import { profileMode, readProfileSession } from "../api";

// Internal regressions for a browser-observed integration failure; not acceptance.
describe("profile requests through Langflow's locale interceptor", () => {
	const originalFetch = global.fetch;
	const originalHeaders = global.Headers;
	const timeoutDescriptor = Object.getOwnPropertyDescriptor(
		AbortSignal,
		"timeout",
	);

	beforeEach(() => {
		global.Headers = jest.fn(
			(input) => new Map(Object.entries(input || {})),
		) as unknown as typeof Headers;
		Object.defineProperty(AbortSignal, "timeout", {
			configurable: true,
			value: () => new AbortController().signal,
		});
	});
	afterEach(() => {
		global.fetch = originalFetch;
		global.Headers = originalHeaders;
		if (timeoutDescriptor)
			Object.defineProperty(AbortSignal, "timeout", timeoutDescriptor);
		else delete (AbortSignal as any).timeout;
	});

	function intercepted(body: unknown) {
		global.fetch = jest.fn(async (_url, options) => {
			// This is the actual pinned interceptor's previously failing contract.
			(options!.headers as Record<string, string>)["Accept-Language"] = "en";
			return {
				ok: true,
				json: async () => body,
				headers: { get: () => null },
			} as unknown as Response;
		});
	}

	it("supplies mutable headers even for a plain GET", async () => {
		intercepted({ enabled: false });
		await expect(profileMode()).resolves.toBe(false);
		expect(global.fetch).toHaveBeenCalledWith(
			"/api/v1/laomedo/profile-mode",
			expect.objectContaining({ headers: { "Accept-Language": "en" } }),
		);
	});

	it("checks the session through the same contract and projects safe identity only", async () => {
		intercepted({
			authenticated: true,
			user: { id: "profile-id" },
			store_api_key: "must-not-escape",
		});
		const result = await readProfileSession();
		expect(result).toEqual({ authenticated: true, profileId: "profile-id" });
		expect(JSON.stringify(result)).not.toContain("must-not-escape");
	});
});
