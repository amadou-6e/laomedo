import { useEffect, useState, type ReactNode } from "react";
import ErrorExplanation from "@/components/laomedoErrors/ErrorExplanation";
import { describeNodeFailure } from "@/components/laomedoErrors/nodeErrors";
import { Button } from "@/components/ui/button";
import ProfileEntry from "./ProfileEntry";
import { listProfiles, profileMode, type ProfileIndex } from "./api";

export default function ProfileEntryGate({
	children,
}: {
	children: ReactNode;
}) {
	const [state, setState] = useState<{
		enabled?: boolean;
		index?: ProfileIndex;
		failed?: boolean;
	}>({});
	const [attempt, setAttempt] = useState(0);
	useEffect(() => {
		const controller = new AbortController();
		setState({});
		(async () => {
			try {
				const enabled = await profileMode(controller.signal);
				const index = enabled
					? await listProfiles(controller.signal)
					: undefined;
				if (!controller.signal.aborted) setState({ enabled, index });
			} catch {
				if (!controller.signal.aborted) setState({ failed: true });
			}
		})();
		return () => controller.abort();
	}, [attempt]);
	if (state.enabled === false) return <>{children}</>;
	if (state.index) return <ProfileEntry initial={state.index} />;
	return (
		<main className="flex min-h-svh items-center justify-center p-6">
			<section className="w-full max-w-md rounded-xl border p-6">
				{state.failed ? (
					<>
						<h1 className="text-xl font-semibold">
							Profiles could not be loaded
						</h1>
						<div className="mt-4 text-sm">
							<ErrorExplanation
								failure={describeNodeFailure(
									"profile_list_unavailable",
									undefined,
									{ operation: "load profiles" },
								)}
							/>
						</div>
						<Button
							className="mt-4"
							onClick={() => setAttempt((value) => value + 1)}
						>
							Reload profiles
						</Button>
					</>
				) : (
					<p role="status" className="flex items-center gap-2 text-sm">
						<span
							aria-hidden="true"
							className="inline-block size-4 animate-spin rounded-full border-2 border-current border-t-transparent"
						/>
						Loading profiles…
					</p>
				)}
			</section>
		</main>
	);
}
