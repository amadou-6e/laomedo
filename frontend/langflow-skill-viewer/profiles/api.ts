export type ProfileSummary = { id: string; name: string };
export type ProfileIndex = { profiles: ProfileSummary[]; pin_digits: number };

const publicCodes = new Set([
	"profile_input_invalid",
	"profile_name_unavailable",
	"profile_list_unavailable",
	"profile_creation_unconfirmed",
	"profile_request_refused",
	"profile_setup_unavailable",
]);

export class ProfileFailure extends Error {
	constructor(
		public code: string,
		public waitSeconds = 0,
	) {
		super(code);
	}
}

function retryWait(value: string | null): number {
	if (!value) return 0;
	const seconds = /^\d+$/.test(value)
		? Number(value)
		: Math.ceil((Date.parse(value) - Date.now()) / 1000);
	return Number.isFinite(seconds) ? Math.max(0, seconds) : 0;
}

async function readJson(response: Response, fallback: string) {
	let body: any;
	try {
		body = await response.json();
	} catch {
		throw new ProfileFailure(fallback);
	}
	if (!response.ok) {
		throw new ProfileFailure(
			publicCodes.has(body?.code) ? body.code : fallback,
			retryWait(response.headers.get("Retry-After")),
		);
	}
	return body;
}

async function request(
	url: string,
	options: RequestInit = {},
): Promise<Response> {
	const timeout = AbortSignal.timeout(15000);
	const signal = options.signal
		? AbortSignal.any([options.signal, timeout])
		: timeout;
	// The pinned app fetch interceptor writes its locale headers in place.
	const headers = Object.fromEntries(new Headers(options.headers).entries());
	return fetch(url, { ...options, headers, signal });
}

export async function profileMode(signal?: AbortSignal): Promise<boolean> {
	const response = await request("/api/v1/laomedo/profile-mode", {
		credentials: "same-origin",
		cache: "no-store",
		signal,
	});
	const body = await readJson(response, "profile_list_unavailable");
	if (typeof body?.enabled !== "boolean")
		throw new ProfileFailure("profile_list_unavailable");
	if (
		body.enabled &&
		(typeof BroadcastChannel !== "function" ||
			typeof crypto.randomUUID !== "function")
	) {
		throw new ProfileFailure("profile_browser_unsupported");
	}
	return body.enabled;
}

export async function listProfiles(
	signal?: AbortSignal,
): Promise<ProfileIndex> {
	const response = await request("/api/v1/laomedo/profiles", {
		credentials: "same-origin",
		cache: "no-store",
		signal,
	});
	const body = await readJson(response, "profile_list_unavailable");
	if (
		body?.pin_digits !== 6 ||
		!Array.isArray(body.profiles) ||
		body.profiles.some(
			(item: any) =>
				typeof item?.id !== "string" || typeof item?.name !== "string",
		)
	) {
		throw new ProfileFailure("profile_list_unavailable");
	}
	return body;
}

export async function createProfile(
	name: string,
	pin: string,
	confirmation: string,
): Promise<ProfileSummary> {
	let response: Response;
	try {
		response = await request("/api/v1/laomedo/profiles", {
			method: "POST",
			credentials: "same-origin",
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify({ name, pin, confirmation }),
		});
	} catch {
		throw new ProfileFailure("profile_creation_unconfirmed");
	}
	const body = await readJson(response, "profile_creation_unconfirmed");
	if (typeof body?.id !== "string" || body?.name !== name.trim())
		throw new ProfileFailure("profile_creation_unconfirmed");
	return body;
}

export async function enterProfile(profile: ProfileSummary, pin: string) {
	let response: Response;
	try {
		response = await request("/api/v1/login", {
			method: "POST",
			credentials: "same-origin",
			headers: { "Content-Type": "application/x-www-form-urlencoded" },
			body: new URLSearchParams({
				username: profile.name,
				password: pin,
			}).toString(),
		});
	} catch {
		throw new ProfileFailure("profile_entry_unconfirmed");
	}
	if (response.status === 429)
		throw new ProfileFailure(
			"profile_rate_limited",
			retryWait(response.headers.get("Retry-After")),
		);
	if ([400, 401, 403].includes(response.status))
		throw new ProfileFailure("profile_pin_rejected");
	const tokens = await readJson(response, "profile_entry_unconfirmed");
	const current = await request("/api/v1/users/whoami", {
		credentials: "same-origin",
		cache: "no-store",
	});
	const user = await readJson(current, "profile_entry_unconfirmed");
	if (
		user.id !== profile.id ||
		user.username !== profile.name ||
		user.is_superuser ||
		!user.is_active ||
		typeof tokens?.access_token !== "string"
	) {
		throw new ProfileFailure("profile_entry_unconfirmed");
	}
	// Cookies are upstream-owned; do not pass credential values to UI state.
	return;
}

export async function readProfileSession(): Promise<{
	authenticated: boolean;
	profileId?: string;
}> {
	const response = await request("/api/v1/session", {
		credentials: "same-origin",
		cache: "no-store",
	});
	const body = await readJson(response, "app_signout_unconfirmed");
	if (
		typeof body?.authenticated !== "boolean" ||
		(body.authenticated && typeof body.user?.id !== "string")
	)
		throw new ProfileFailure("app_signout_unconfirmed");
	return {
		authenticated: body.authenticated,
		profileId: body.authenticated ? body.user.id : undefined,
	};
}
