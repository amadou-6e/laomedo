import { useContext, useEffect, useState } from "react";
import { useLogout } from "@/controllers/API/queries/auth";
import { AuthContext } from "@/contexts/authContext";
import useAuthStore from "@/stores/authStore";
import PopupFrame, {
	popupButtonStyle,
} from "@/components/laomedoRecovery/PopupFrame";
import ErrorExplanation from "@/components/laomedoErrors/ErrorExplanation";
import { describeNodeFailure } from "@/components/laomedoErrors/nodeErrors";
import { profileMode } from "./api";

import { announceProfileChange } from "./ProfileSessionSync";

export default function useProfileSessionActions() {
	const [enabled, setEnabled] = useState<boolean>();
	const [open, setOpen] = useState(false);
	const [checking, setChecking] = useState(false);
	const [intent, setIntent] = useState<"switch" | "logout">("switch");
	const { clearAuthSession, userData } = useContext(AuthContext);
	const { mutate, isPending } = useLogout();
	useEffect(() => {
		let current = true;
		profileMode()
			.then((value) => {
				if (current) setEnabled(value);
			})
			.catch(() => {
				if (current) setEnabled(false);
			});
		return () => {
			current = false;
		};
	}, []);

	function finish() {
		if (enabled) announceProfileChange();
		clearAuthSession();
		window.location.assign("/login");
	}
	function signOut(next: "switch" | "logout") {
		setIntent(next);
		setOpen(true);
		mutate(undefined, {
			onSuccess: finish,
			onError: () => setOpen(true),
		});
	}
	async function check() {
		setChecking(true);
		try {
			const response = await fetch("/api/v1/session", {
				credentials: "same-origin",
				cache: "no-store",
				signal: AbortSignal.timeout(15000),
			});
			if (!response.ok) return;
			const session = await response.json();
			if (session.authenticated === false) {
				useAuthStore.getState().logout();
				finish();
			} else if (session.authenticated === true) {
				if (session.user?.id === userData?.id) setOpen(false);
				else window.location.replace("/login");
			}
		} catch {
			/* Keep the unconfirmed state and its safe explanation. */
		} finally {
			setChecking(false);
		}
	}
	const failure = describeNodeFailure("app_signout_unconfirmed", undefined, {
		operation: intent === "switch" ? "switch profile" : "log out",
	});
	const notice = open ? (
		<PopupFrame
			label="Sign-out not confirmed"
			code="app_signout_unconfirmed"
			onClose={() => {
				if (!isPending && !checking) setOpen(false);
			}}
			heading={
				<h3 className="text-sm font-bold">
					{isPending
						? "Signing out..."
						: checking
							? "Checking current profile..."
							: failure.title}
				</h3>
			}
			footer={
				<>
					<button
						type="button"
						style={popupButtonStyle}
						disabled={isPending || checking}
						onClick={() => signOut(intent)}
					>
						Retry {intent === "switch" ? "switch" : "sign-out"}
					</button>
					<button
						type="button"
						style={popupButtonStyle}
						disabled={isPending || checking}
						onClick={check}
					>
						Check current profile
					</button>
				</>
			}
		>
			{isPending || checking ? (
				<p role="status" className="flex items-center gap-2">
					<span
						aria-hidden="true"
						className="inline-block size-4 animate-spin rounded-full border-2 border-current border-t-transparent"
					/>
					{checking ? "Checking current profile…" : "Signing out…"}
				</p>
			) : (
				<ErrorExplanation failure={failure} />
			)}
		</PopupFrame>
	) : null;
	return {
		enabled,
		ready: enabled !== undefined,
		busy: isPending || checking,
		signOut,
		notice,
	};
}
