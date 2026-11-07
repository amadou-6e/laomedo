import { useContext, useEffect, useState } from "react";
import { AuthContext } from "@/contexts/authContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import ErrorExplanation from "@/components/laomedoErrors/ErrorExplanation";
import { describeNodeFailure } from "@/components/laomedoErrors/nodeErrors";
import {
	createProfile,
	enterProfile,
	listProfiles,
	ProfileFailure,
	type ProfileIndex,
	type ProfileSummary,
} from "./api";

import { announceProfileChange } from "./ProfileSessionSync";

type Screen =
	| "picker"
	| "create"
	| "enter"
	| "saved"
	| "uncertain"
	| "name-unavailable";

export default function ProfileEntry({
	initial,
	initialCreate = false,
}: {
	initial: ProfileIndex;
	initialCreate?: boolean;
}) {
	const { login, clearAuthSession } = useContext(AuthContext);
	const [profiles, setProfiles] = useState(initial.profiles);
	const [screen, setScreen] = useState<Screen>(
		initialCreate ? "create" : "picker",
	);
	const [selected, setSelected] = useState<ProfileSummary | null>(null);
	const [name, setName] = useState("");
	const [pin, setPin] = useState("");
	const [confirmation, setConfirmation] = useState("");
	const [pending, setPending] = useState("");
	const [error, setError] = useState("");
	const [wait, setWait] = useState(0);

	useEffect(() => {
		if (!wait) return;
		const timer = window.setTimeout(
			() => setWait((value) => Math.max(0, value - 1)),
			1000,
		);
		return () => window.clearTimeout(timer);
	}, [wait]);

	const failure = error
		? describeNodeFailure(error, undefined, { operation: "profile entry" })
		: null;
	const clearPin = () => {
		setPin("");
		setConfirmation("");
	};
	const back = () => {
		clearPin();
		setError("");
		setScreen("picker");
		setSelected(null);
	};

	async function open(
		profile: ProfileSummary,
		value: string,
		newlySaved = false,
	) {
		setPending("Opening profile…");
		try {
			const tokens = await enterProfile(profile, value);
			clearPin();
			clearAuthSession();
			login(tokens.access_token, "login", tokens.refresh_token);
			announceProfileChange();
		} catch (caught) {
			clearPin();
			const failure =
				caught instanceof ProfileFailure
					? caught
					: new ProfileFailure("profile_entry_unconfirmed");
			setError(failure.code);
			setWait(failure.waitSeconds);
			if (newlySaved) setScreen("saved");
		} finally {
			setPending("");
		}
	}

	async function submit(event: React.FormEvent) {
		event.preventDefault();
		setError("");
		if (screen === "create") {
			if (!name.trim() || !/^[0-9]{6}$/.test(pin) || pin !== confirmation) {
				setError("profile_input_invalid");
				return;
			}
			setPending("Creating profile…");
			try {
				const profile = await createProfile(name, pin, confirmation);
				setSelected(profile);
				setProfiles((current) => [
					...current.filter((item) => item.id !== profile.id),
					profile,
				]);
				setScreen("enter");
				await open(profile, pin, true);
			} catch (caught) {
				const failure =
					caught instanceof ProfileFailure
						? caught
						: new ProfileFailure("profile_creation_unconfirmed");
				setError(failure.code);
				clearPin();
				if (failure.code === "profile_creation_unconfirmed")
					setScreen("uncertain");
				if (failure.code === "profile_name_unavailable")
					setScreen("name-unavailable");
			} finally {
				setPending("");
			}
		} else if (selected) {
			if (!/^[0-9]{6}$/.test(pin)) {
				setError("profile_input_invalid");
				return;
			}
			await open(selected, pin);
		}
	}

	async function reconcile() {
		setPending("Checking whether the profile was saved…");
		setError("");
		try {
			const index = await listProfiles();
			setProfiles(index.profiles);
			const saved = index.profiles.find((item) => item.name === name.trim());
			if (saved) {
				setSelected(saved);
				setScreen("saved");
			} else setError("profile_creation_unconfirmed");
		} catch {
			setError("profile_list_unavailable");
		} finally {
			setPending("");
		}
	}

	return (
		<main className="flex min-h-svh items-center justify-center bg-background px-6 py-10">
			<section
				className="w-full max-w-md rounded-xl border bg-background p-6 shadow-sm"
				aria-labelledby="profile-title"
			>
				<h1 id="profile-title" className="text-xl font-semibold">
					{screen === "create"
						? "Create profile"
						: screen === "name-unavailable"
							? "Choose another name"
							: screen === "saved"
								? "Profile saved"
								: screen === "uncertain"
									? "Profile save not confirmed"
									: screen === "enter"
										? "Open profile"
										: profiles.length
											? "Choose profile"
											: "No profiles yet"}
				</h1>
				<p className="mt-2 text-sm text-muted-foreground">
					A setup on this machine. No email or administrator required.
				</p>
				{screen === "picker" ? (
					<div className="mt-6 flex flex-col gap-3">
						{profiles.map((profile) => (
							<Button
								key={profile.id}
								variant="outline"
								onClick={() => {
									setSelected(profile);
									setScreen("enter");
								}}
							>
								{profile.name}
							</Button>
						))}
						<Button
							onClick={() => {
								clearPin();
								setScreen("create");
							}}
						>
							{profiles.length ? "Create another profile" : "Create profile"}
						</Button>
					</div>
				) : screen === "name-unavailable" ? (
					<div className="mt-6 space-y-4">
						<p className="text-sm">
							This name is unavailable. Your profile has not been created.
						</p>
						<Button
							onClick={() => {
								setError("");
								setScreen("create");
							}}
						>
							Edit name
						</Button>
						<Button variant="outline" onClick={back}>
							Back to profiles
						</Button>
					</div>
				) : screen === "saved" ? (
					<div className="mt-6 space-y-4">
						<p className="text-sm">
							Your profile exists. Enter its PIN to open it. Do not create it
							again.
						</p>
						<Button
							onClick={() => {
								setError("");
								setScreen("enter");
							}}
						>
							Open existing profile
						</Button>
					</div>
				) : screen === "uncertain" ? (
					<div className="mt-6 space-y-4">
						<p className="text-sm">
							Check the profile list before trying to create it again.
						</p>
						<Button disabled={!!pending} onClick={reconcile}>
							Check profile list
						</Button>
						<Button variant="outline" disabled={!!pending} onClick={back}>
							Back to profiles
						</Button>
					</div>
				) : (
					<form onSubmit={submit} className="mt-6 space-y-4">
						{screen === "create" ? (
							<label className="block text-sm">
								Profile name
								<Input
									className="mt-1"
									value={name}
									onChange={(event) => setName(event.target.value)}
									maxLength={40}
									required
									disabled={!!pending}
									autoComplete="off"
								/>
							</label>
						) : (
							<p className="text-sm">
								Selected profile: <strong>{selected?.name}</strong>
							</p>
						)}
						<label className="block text-sm">
							PIN
							<Input
								className="mt-1"
								type="password"
								inputMode="numeric"
								autoComplete="off"
								maxLength={6}
								pattern="[0-9]{6}"
								value={pin}
								onChange={(event) => setPin(event.target.value)}
								required
								disabled={!!pending || !!wait}
							/>
						</label>
						{screen === "create" && (
							<label className="block text-sm">
								Confirm PIN
								<Input
									className="mt-1"
									type="password"
									inputMode="numeric"
									autoComplete="off"
									maxLength={6}
									pattern="[0-9]{6}"
									value={confirmation}
									onChange={(event) => setConfirmation(event.target.value)}
									required
									disabled={!!pending}
								/>
							</label>
						)}
						<div className="flex flex-col gap-2 pt-2">
							<Button type="submit" disabled={!!pending || !!wait}>
								{screen === "create" ? "Create profile" : "Open profile"}
							</Button>
							<Button
								type="button"
								variant="outline"
								disabled={!!pending}
								onClick={back}
							>
								Back to profiles
							</Button>
						</div>
					</form>
				)}
				{pending && (
					<p role="status" className="mt-4 flex items-center gap-2 text-sm">
						<span
							aria-hidden="true"
							className="inline-block size-4 animate-spin rounded-full border-2 border-current border-t-transparent"
						/>
						{pending}
					</p>
				)}
				{!!wait && (
					<p role="status" className="mt-4 text-sm">
						Try again in {wait} seconds.
					</p>
				)}
				{failure && !pending && (
					<div
						role="alert"
						className="mt-4 rounded border border-red-200 p-3 text-sm"
					>
						<p className="font-medium">{failure.title}</p>
						<ErrorExplanation failure={failure} />
					</div>
				)}
			</section>
		</main>
	);
}
