import { useEffect, useState } from "react";
import { ChevronRight, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
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

type ProfileField = "name" | "pin" | "confirmation";

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
	const [fieldErrors, setFieldErrors] = useState<Partial<Record<ProfileField, string>>>({});
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
		setFieldErrors({});
		setPin("");
		setConfirmation("");
	};
	const clearValidationError = (field: ProfileField) => {
		setFieldErrors((current) => ({ ...current, [field]: "" }));
		setError((current) =>
			current === "profile_input_invalid" || current === "profile_pin_invalid"
				? ""
				: current,
		);
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
			await enterProfile(profile, value);
			clearPin();
			announceProfileChange();
			// Restore the confirmed cookie session in a fresh document. No old
			// query, mutation or store callback can refill the next profile.
			window.location.replace("/");
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
		setFieldErrors({});
		if (screen === "create") {
			const invalid: Partial<Record<ProfileField, string>> = {};
			if (!name.trim()) invalid.name = "profile_name_required";
			if (!/^[0-9]{6}$/.test(pin)) invalid.pin = "profile_pin_invalid";
			if (!confirmation) invalid.confirmation = "profile_confirmation_required";
			else if (pin !== confirmation) invalid.confirmation = "profile_pin_mismatch";
			if (Object.keys(invalid).length) {
				setFieldErrors(invalid);
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
				setFieldErrors({ pin: "profile_pin_invalid" });
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
		<main className="fixed inset-0 z-50 flex flex-col overflow-y-auto bg-background p-6">
			<section
				className="mx-auto my-auto w-full max-w-md shrink-0 rounded-xl border bg-background p-6 shadow-sm"
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
					{screen === "picker" ? "Select a profile to continue." : screen === "create" ? "Create a local profile with a six-digit PIN." : "Enter your PIN to continue."}
				</p>
				{screen === "picker" ? (
					<div className="mt-6">
						<div className="divide-y divide-border overflow-hidden rounded-lg border">
						{profiles.map((profile) => (
							<Button
								key={profile.id}
								variant="ghost"
								className="h-auto min-h-16 w-full justify-start gap-3 rounded-none px-4 py-3 text-left font-normal focus-visible:ring-inset"
								ignoreTitleCase
								onClick={() => {
									clearPin();
									setError("");
									setSelected(profile);
									setScreen("enter");
								}}
							>
								<span aria-hidden="true" className="flex size-9 shrink-0 items-center justify-center rounded-full bg-muted text-sm font-medium text-muted-foreground">
									{profile.name.trim().split(/\s+/).slice(0, 2).map((word) => Array.from(word)[0]).join("").toLocaleUpperCase()}
								</span>
								<span className="min-w-0 flex-1 whitespace-normal break-words">{profile.name}</span>
								<ChevronRight aria-hidden="true" className="size-4 shrink-0 text-muted-foreground" />
							</Button>
						))}
						</div>
						<div className="mt-4 border-t pt-3">
						<Button
							variant="ghost"
							ignoreTitleCase
							className="w-full justify-start gap-3 px-4 font-normal"
							onClick={() => {
								clearPin();
								setError("");
								setScreen("create");
							}}
						>
							<Plus aria-hidden="true" className="size-5 shrink-0" />
							Create profile
						</Button>
						</div>
					</div>
				) : screen === "name-unavailable" ? (
					<div className="mt-6 flex flex-col gap-4">
						<p className="text-sm">
							This name is unavailable. Your profile has not been created.
						</p>
						<Button
							onClick={() = ignoreTitleCase> {
								setError("");
								setScreen("create");
							}}
						>
							Edit name
						</Button>
						<Button variant="outline" onClick={back} ignoreTitleCase>
							Back to profiles
						</Button>
					</div>
				) : screen === "saved" ? (
					<div className="mt-6 flex flex-col gap-4">
						<p className="text-sm">
							Your profile exists. Enter its PIN to open it. Do not create it
							again.
						</p>
						<Button
							onClick={() = ignoreTitleCase> {
								setError("");
								setScreen("enter");
							}}
						>
							Open existing profile
						</Button>
					</div>
				) : screen === "uncertain" ? (
					<div className="mt-6 flex flex-col gap-4">
						<p className="text-sm">
							Check the profile list before trying to create it again.
						</p>
						<Button disabled={!!pending} onClick={reconcile} ignoreTitleCase>
							Check profile list
						</Button>
						<Button variant="outline" disabled={!!pending} onClick={back} ignoreTitleCase>
							Back to profiles
						</Button>
					</div>
				) : (
					<form noValidate onSubmit={submit} className="mt-6 flex flex-col gap-4">
						{screen === "create" ? (
							<label className="block text-sm">
								Profile name
								<Input
									className="mt-1"
									aria-label="Profile name" value={name}
									onChange={(event) => {
										setName(event.target.value);
										clearValidationError("name");
									}}
									maxLength={40}
									required
									disabled={!!pending}
									autoComplete="off"
									aria-invalid={!!fieldErrors.name}
									aria-describedby={fieldErrors.name ? "profile-name-error" : undefined}
								/>
								{fieldErrors.name && <p id="profile-name-error" role="alert" className="mt-2 text-sm text-red-600 dark:text-red-400">{describeNodeFailure(fieldErrors.name).title}</p>}
							</label>
						) : (
							<p className="text-sm">
								Selected profile: <strong>{selected?.name}</strong>
							</p>
						)}
						<label className="block text-sm">
							PIN (6 digits)
							<Input
								className="mt-1"
								type="password"
								inputMode="numeric"
								autoComplete="off"
								maxLength={6}
								pattern="[0-9]{6}"
								aria-label="PIN (6 digits)" value={pin}
								onChange={(event) => {
									setPin(event.target.value);
									clearValidationError("pin");
									clearValidationError("confirmation");
								}}
								required
								disabled={!!pending || !!wait}
								aria-invalid={!!fieldErrors.pin}
								aria-describedby={fieldErrors.pin ? "profile-pin-error" : undefined}
							/>
							{fieldErrors.pin && <p id="profile-pin-error" role="alert" className="mt-2 text-sm text-red-600 dark:text-red-400">{describeNodeFailure(fieldErrors.pin).title}</p>}
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
									aria-label="Confirm PIN" value={confirmation}
									onChange={(event) => {
										setConfirmation(event.target.value);
										clearValidationError("confirmation");
									}}
									required
									disabled={!!pending}
									aria-invalid={!!fieldErrors.confirmation}
									aria-describedby={fieldErrors.confirmation ? "profile-confirmation-error" : undefined}
								/>
								{fieldErrors.confirmation && <p id="profile-confirmation-error" role="alert" className="mt-2 text-sm text-red-600 dark:text-red-400">{describeNodeFailure(fieldErrors.confirmation).title}</p>}
							</label>
						)}
						<div className="flex flex-col gap-2 pt-2">
							<Button type="submit" disabled={!!pending || !!wait} ignoreTitleCase>
								{screen === "create" ? "Create profile" : "Open profile"}
							</Button>
							<Button
								type="button"
								variant="outline"
								disabled={!!pending}
								onClick={back}
							 ignoreTitleCase>
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
						<p>{failure.description}</p>
						{failure.recovery && <p className="mt-2">{failure.recovery}</p>}
					</div>
				)}
			</section>
		</main>
	);
}
