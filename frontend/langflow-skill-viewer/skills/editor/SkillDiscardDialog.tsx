import * as Dialog from "@radix-ui/react-dialog";
import { useRef } from "react";

/** Confirm only working-copy loss; cancellation never touches buffers/history. */
export default function SkillDiscardDialog({ open, disabled, cancel, confirm, restoreFocus }: {
  open: boolean; disabled: boolean; cancel: () => void; confirm: () => void; restoreFocus: () => void;
}) {
  const keep = useRef<HTMLButtonElement>(null);
  return <Dialog.Root open={open} onOpenChange={(value) => { if (!value) cancel(); }}>
    <Dialog.Portal>
      <Dialog.Overlay className="fixed inset-0 z-[60] bg-black/40" />
      <Dialog.Content role="alertdialog" className="fixed left-1/2 top-1/2 z-[61] w-[calc(100dvw-2rem)] max-w-md -translate-x-1/2 -translate-y-1/2 rounded-lg border bg-background p-4 text-foreground shadow-lg"
        onOpenAutoFocus={(event) => { event.preventDefault(); keep.current?.focus(); }}
        onCloseAutoFocus={(event) => { event.preventDefault(); restoreFocus(); }}
        onEscapeKeyDown={(event) => { event.preventDefault(); event.stopImmediatePropagation(); cancel(); }}
        onKeyDown={(event) => { event.stopPropagation(); }}>
        <Dialog.Title className="text-sm font-semibold">Discard changes?</Dialog.Title>
        <Dialog.Description className="mt-2 text-sm text-muted-foreground">Your unsaved changes will be lost. Saved history is kept.</Dialog.Description>
        <div className="mt-4 flex flex-wrap justify-end gap-2 text-sm">
          <button ref={keep} type="button" className="rounded border px-3 py-1.5" onClick={cancel}>Keep editing</button>
          <button type="button" disabled={disabled} className="rounded border bg-primary px-3 py-1.5 text-primary-foreground disabled:opacity-50" onClick={() => { if (!disabled) confirm(); }}>Discard changes</button>
        </div>
      </Dialog.Content>
    </Dialog.Portal>
  </Dialog.Root>;
}
