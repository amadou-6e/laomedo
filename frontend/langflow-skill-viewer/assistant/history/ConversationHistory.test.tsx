import { fireEvent, render, screen } from "@testing-library/react";
import ConversationHistory from "./ConversationHistory";

jest.mock("../ProviderIcon", () => ({ __esModule: true, default: () => null }));

test("history divider resizes within bounds and a drag never toggles the panel", () => {
  const clientWidth = jest.spyOn(HTMLElement.prototype, "clientWidth", "get").mockReturnValue(1000);
  const pointerEvent = window.PointerEvent;
  window.PointerEvent = MouseEvent as typeof PointerEvent;
  const onToggle = jest.fn();
  const onIndex = jest.fn();
  const onSelect = jest.fn();
  try {
    render(<div><ConversationHistory index={{conversations: [], next_cursor: null}} onIndex={onIndex}
      generation={{current: 0}} owner="owner" selected="" embedded={false} history
      historyControl={null} headerActions={null} fail={jest.fn()} onSelect={onSelect}
      onNew={jest.fn()} onToggle={onToggle} /></div>);
    expect(screen.getByRole("heading", {name: "History"})).toBeVisible();
    const divider = screen.getByRole("separator", {name: "Resize history"});
    const button = screen.getByRole("button", {name: "Collapse conversations"});
    let captured = false;
    button.setPointerCapture = () => {captured = true;};
    button.hasPointerCapture = () => captured;
    button.releasePointerCapture = () => {captured = false;};
    fireEvent.pointerDown(button, {button: 0, clientX: 256, pointerId: 1});
    fireEvent.pointerMove(button, {clientX: 356, pointerId: 1});
    expect(divider).toHaveAttribute("aria-valuenow", "356");
    fireEvent.pointerUp(button, {pointerId: 1});
    fireEvent.click(button, {detail: 1});
    expect(onToggle).not.toHaveBeenCalled();
    fireEvent.click(button, {detail: 1});
    expect(onToggle).toHaveBeenCalledTimes(1);
    fireEvent.keyDown(divider, {key: "Home"});
    expect(divider).toHaveAttribute("aria-valuenow", "180");
    fireEvent.keyDown(divider, {key: "ArrowLeft"});
    expect(divider).toHaveAttribute("aria-valuenow", "180");
    fireEvent.keyDown(divider, {key: "End"});
    expect(divider).toHaveAttribute("aria-valuenow", "480");
    expect(onIndex).not.toHaveBeenCalled();
    expect(onSelect).not.toHaveBeenCalled();
  } finally {
    clientWidth.mockRestore();
    window.PointerEvent = pointerEvent;
  }
});
