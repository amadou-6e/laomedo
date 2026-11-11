import { fireEvent, render, screen } from "@testing-library/react";
import ProfileEntry from "../ProfileEntry";

jest.mock("@/components/ui/button", () => ({
	Button: ({ ignoreTitleCase, variant, children, ...props }) => (
		<button {...props}>{children}</button>
	),
}));
jest.mock("@/components/ui/input", () => ({
	Input: (props) => <input {...props} />,
}));
jest.mock("../ProfileSessionSync", () => ({ announceProfileChange: jest.fn() }));
jest.mock("../api", () => ({
	createProfile: jest.fn(),
	enterProfile: jest.fn(),
	listProfiles: jest.fn(),
}));

describe("profile entry validation recovery", () => {
	it("removes stale validation feedback when a creation field is corrected", () => {
		render(<ProfileEntry initial={{ profiles: [], pin_digits: 6 }} initialCreate />);
		fireEvent.click(screen.getByRole("button", { name: "Create profile" }));
		expect(screen.getByText("Enter a profile name")).toBeTruthy();
		expect(screen.getByLabelText("Profile name").getAttribute("aria-invalid")).toBe("true");
		expect(screen.queryByText("Technical details")).toBeNull();
		fireEvent.change(screen.getByLabelText("Profile name"), {
			target: { value: "Work" },
		});
		expect(screen.queryByText("Enter a profile name")).toBeNull();
		expect(screen.getByText("Use a six-digit PIN")).toBeTruthy();
	});

	it("starts another entry screen without the previous form error", () => {
		render(
			<ProfileEntry initial={{ profiles: [{ id: "work", name: "Work" }], pin_digits: 6 }} />,
		);
		fireEvent.click(screen.getByRole("button", { name: "Work" }));
		fireEvent.click(screen.getByRole("button", { name: "Log in" }));
		expect(screen.getByRole("alert")).toBeTruthy();
		fireEvent.click(screen.getByRole("button", { name: "Back to profiles" }));
		const profile = screen.getByRole("button", { name: "Work" });
		expect(profile.querySelector('svg[aria-hidden="true"]')).toBeTruthy();
		fireEvent.click(profile);
		expect(screen.queryByRole("alert")).toBeNull();
	});

	it("identifies mismatched PINs at confirmation and preserves the entered name", () => {
		render(<ProfileEntry initial={{ profiles: [], pin_digits: 6 }} initialCreate />);
		fireEvent.change(screen.getByLabelText("Profile name"), { target: { value: "Work" } });
		fireEvent.change(screen.getByLabelText("PIN (6 digits)"), { target: { value: "012345" } });
		fireEvent.change(screen.getByLabelText("Confirm PIN"), { target: { value: "012346" } });
		fireEvent.click(screen.getByRole("button", { name: "Create profile" }));
		expect(screen.getByText("PINs don't match")).toBeTruthy();
		expect(screen.getByLabelText("Confirm PIN").getAttribute("aria-describedby")).toBe("profile-confirmation-error");
		expect((screen.getByLabelText("Profile name") as HTMLInputElement).value).toBe("Work");
	});
});
