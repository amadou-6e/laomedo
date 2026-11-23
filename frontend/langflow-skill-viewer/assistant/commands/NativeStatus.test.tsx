import { fireEvent, render, screen } from "@testing-library/react";
import NativeStatus from "./NativeStatus";
import { nativeStatus } from "./statusFields";

test("renders reported quota without inventing context usage and supports dismissal", () => {
  render(<NativeStatus conversation="chat-id" text={"**Session:** `native-thread`\n**Context window:** data not available yet\n**codex Weekly limit:** 50% left (resets 11:55 on Nov 23)"} />);
  expect(screen.getByText("chat-id")).toBeVisible();
  expect(screen.getByText("native-thread")).toBeVisible();
  expect(screen.getByText("data not available yet")).toBeVisible();
  expect(screen.getByRole("meter")).toHaveAttribute("aria-valuenow", "50");
  fireEvent.click(screen.getByRole("button", { name: "Close status" }));
  expect(screen.queryByRole("meter")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Show status" }));
  expect(screen.getByRole("meter")).toBeVisible();
});

test("unrecognized native text remains readable and invalid percentages get no meter", () => {
  const { rerender } = render(<NativeStatus conversation="chat" text="New native status format" />);
  expect(screen.getByText("New native status format")).toBeVisible();
  rerender(<NativeStatus conversation="chat" text="**Session ID:** renamed-native-thread" />);
  expect(screen.getByText("**Session ID:** renamed-native-thread")).toBeVisible();
  rerender(<NativeStatus conversation="chat" text="**Weekly limit:** 150% left" />);
  expect(screen.queryByRole("meter")).toBeNull();
  expect(nativeStatus("**Weekly limit:** 150% left").limits[0].remaining).toBeNull();
});
