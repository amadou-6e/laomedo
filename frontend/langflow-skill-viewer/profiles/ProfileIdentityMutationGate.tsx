import { useEffect, useState, type ReactNode } from "react";
import { profileMode } from "./api";

/** Preserve native identity editors only outside the opt-in profile runtime. */
export default function ProfileIdentityMutationGate({
	children,
}: {
	children: ReactNode;
}) {
	const [nativeMode, setNativeMode] = useState(false);
	useEffect(() => {
		let current = true;
		profileMode()
			.then((enabled) => {
				if (current) setNativeMode(!enabled);
			})
			.catch(() => {});
		return () => {
			current = false;
		};
	}, []);
	return nativeMode ? <>{children}</> : null;
}
