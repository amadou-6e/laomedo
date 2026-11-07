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

/** One browser context has one cookie session; discard old documents on change. */
export default function ProfileSessionSync() {
	useEffect(() => {
		let disposed = false;
		let channel: BroadcastChannel | undefined;
		profileMode()
			.then((enabled) => {
				if (!enabled || disposed) return;
				channel = new BroadcastChannel(channelName);
				channel.onmessage = (event) => {
					if (
						event.data?.type === "profile-context-changed" &&
						event.data?.source !== sourceId()
					) {
						window.location.replace("/login");
					}
				};
			})
			.catch(() => {
				/* Entry handles unavailable setup; no identity is inferred. */
			});
		const restore = (event: PageTransitionEvent) => {
			if (event.persisted && channel) window.location.reload();
		};
		window.addEventListener("pageshow", restore);
		return () => {
			disposed = true;
			channel?.close();
			window.removeEventListener("pageshow", restore);
		};
	}, []);
	return null;
}
