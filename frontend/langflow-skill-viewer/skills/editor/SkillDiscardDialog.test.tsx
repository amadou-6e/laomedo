import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import SkillDiscardDialog from "./SkillDiscardDialog";

test("Discard opens a modal popup with safe initial focus; cancel/Escape never confirm", async () => {
  const confirm = jest.fn(), restored = jest.fn();
  function Example() {
    const [open, setOpen] = useState(false);
    return <><button onClick={() => setOpen(true)}>Discard</button>
      <SkillDiscardDialog open={open} disabled={false} cancel={() => setOpen(false)} confirm={confirm} restoreFocus={restored} /></>;
  }
  render(<Example />);
  fireEvent.click(screen.getByRole('button', { name: 'Discard', exact: true }));
  const popup = await screen.findByRole('alertdialog', { name: 'Discard changes?' });
  expect(popup.parentElement).toBe(document.body);
  await waitFor(() => expect(screen.getByRole('button', { name: 'Keep editing' })).toHaveFocus());
  fireEvent.keyDown(popup, { key: 'Escape' });
  await waitFor(() => expect(screen.queryByRole('alertdialog')).toBeNull());
  expect(confirm).not.toHaveBeenCalled(); expect(restored).toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'Discard', exact: true }));
  fireEvent.click(await screen.findByRole('button', { name: 'Keep editing' }));
  expect(confirm).not.toHaveBeenCalled();
});

test("only an enabled explicit confirmation discards", async () => {
  const confirm = jest.fn();
  const props = { open: true, disabled: true, cancel: jest.fn(), confirm, restoreFocus: jest.fn() };
  const { rerender } = render(<SkillDiscardDialog {...props} />);
  const action = await screen.findByRole('button', { name: 'Discard changes', exact: true });
  fireEvent.click(action); expect(confirm).not.toHaveBeenCalled();
  rerender(<SkillDiscardDialog {...props} disabled={false} />);
  fireEvent.click(action); expect(confirm).toHaveBeenCalledTimes(1);
});
