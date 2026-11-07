import { useEffect } from "react";
import { profileMode } from "./api";

const channelName = "laomedo-local-profile-context";
let tabId: string | undefined;
function sourceId() {
	return (tabId ??= crypto.randomUUID());
}

/** No credentials or profile data cross the channel. */
export function announceProfileChange() {
	const channel = new BroadcastChannel(channelName);
	channel.postMessage({ type: "profile-context-changed", source: sourceId() });
	channel.close();
}

/** A new document prevents old requests from filling another profile's stores. */
export default function ProfileSessionSync() {
	useEffect(() => {
		// Subscribe before entry, not after a separate capability request that could
		// fail while the entry page's own request succeeds. Normal previews do not
		// emit these events; receiving one never authenticates or selects a profile.
		if (typeof BroadcastChannel !== "function") return;
		const channel = new BroadcastChannel(channelName);
		channel.onmessage = (event) => {
			if (
				event.data?.type === "profile-context-changed" &&
				event.data?.source !== sourceId()
			) {
				window.location.replace("/login");
			}
		};
		const restore = async (event: PageTransitionEvent) => {
			if (!event.persisted) return;
			try {
				if (await profileMode()) window.location.reload();
			} catch {
				window.location.reload();
			}
		};
		window.addEventListener("pageshow", restore);
		return () => {
			channel.close();
			window.removeEventListener("pageshow", restore);
		};
	}, []);
	return null;
}
