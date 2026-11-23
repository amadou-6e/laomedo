import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import CopyAnswer from "./CopyAnswer";

it("copies exactly the displayed Markdown and reports success", async () => {
  const writeText = jest.fn().mockResolvedValue(undefined);
  Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
  render(<CopyAnswer text={"**Answer**\nsecond line"} />);
  fireEvent.click(screen.getByRole("button", { name: "Copy answer" }));
  await waitFor(() => expect(screen.getByRole("status").textContent).toBe("Copied"));
  expect(writeText).toHaveBeenCalledWith("**Answer**\nsecond line");
});

it("reports clipboard refusal and clears stale feedback when streamed text changes", async () => {
  Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText: jest.fn().mockRejectedValue(new Error("denied")) } });
  const view = render(<CopyAnswer text="First" />);
  fireEvent.click(screen.getByRole("button", { name: "Copy answer" }));
  await waitFor(() => expect(screen.getByRole("status").textContent).toContain("Could not copy"));
  view.rerender(<CopyAnswer text="Second" />);
  expect(screen.getByRole("status").textContent).toBe("");
});
