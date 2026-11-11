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
		expect(screen.getByRole("alert").textContent).toContain("Check your details");
		expect(screen.queryByText("Technical details")).toBeNull();
		fireEvent.change(screen.getByLabelText("Profile name"), {
			target: { value: "Work" },
		});
		expect(screen.queryByRole("alert")).toBeNull();
	});

	it("starts another entry screen without the previous form error", () => {
		render(
			<ProfileEntry initial={{ profiles: [{ id: "work", name: "Work" }], pin_digits: 6 }} />,
		);
		fireEvent.click(screen.getByRole("button", { name: "Work" }));
		fireEvent.click(screen.getByRole("button", { name: "Open profile" }));
		expect(screen.getByRole("alert")).toBeTruthy();
		fireEvent.click(screen.getByRole("button", { name: "Back to profiles" }));
		const profile = screen.getByRole("button", { name: "Work" });
		expect(profile.querySelector('svg[aria-hidden="true"]')).toBeTruthy();
		fireEvent.click(profile);
		expect(screen.queryByRole("alert")).toBeNull();
	});
});
