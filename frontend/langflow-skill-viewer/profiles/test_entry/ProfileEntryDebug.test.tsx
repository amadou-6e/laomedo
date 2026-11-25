import { render, screen } from "@testing-library/react";
import ProfileEntry from "../ProfileEntry";

jest.mock("@/components/ui/button", () => ({
	Button: ({ ignoreTitleCase, variant, children, ...props }) => <button {...props}>{children}</button>,
}));
jest.mock("@/components/ui/input", () => ({ Input: (props) => <input {...props} /> }));
jest.mock("../ProfileSessionSync", () => ({ announceProfileChange: jest.fn() }));
jest.mock("../debug", () => ({ debugPinInput: true }));
jest.mock("../api", () => ({ createProfile: jest.fn(), enterProfile: jest.fn(), listProfiles: jest.fn() }));

it("allows selecting both masked PIN fields only in an opted-in debug build", () => {
	Object.defineProperty(globalThis, "CSS", { configurable: true, value: { supports: () => true } });
	render(<ProfileEntry initial={{ profiles: [], pin_digits: 6 }} initialCreate />);
	for (const label of ["PIN (6 digits)", "Confirm PIN"]) {
		const field = screen.getByLabelText(label);
		expect(field.getAttribute("type")).toBe("text");
		expect(field.style.webkitTextSecurity).toBe("disc");
	}
	expect(screen.getByText("Debug mode: PIN can be copied and read by other software.")).toBeTruthy();
});

it("keeps password fields when visual masking is unavailable", () => {
	Object.defineProperty(globalThis, "CSS", { configurable: true, value: { supports: () => false } });
	render(<ProfileEntry initial={{ profiles: [], pin_digits: 6 }} initialCreate />);
	expect(screen.getByLabelText("PIN (6 digits)").getAttribute("type")).toBe("password");
});
