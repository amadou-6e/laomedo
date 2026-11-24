import type { FormEvent } from "react";
import type { Conversation } from "../models";

export default function ConversationTitle({
  conversation,
  renaming,
  titleDraft,
  savingTitle,
  renameError,
  onSave,
  onDraft,
  onCancel,
  onRename,
}: {
  conversation?: Conversation;
  renaming: boolean;
  titleDraft: string;
  savingTitle: boolean;
  renameError: boolean;
  onSave: (event: FormEvent) => void;
  onDraft: (value: string) => void;
  onCancel: () => void;
  onRename: () => void;
}) {
  return (
    <>
      {renaming && conversation ? (
        <form onSubmit={onSave} className="flex w-full items-center gap-2">
          <input
            autoFocus
            aria-label="Conversation title"
            value={titleDraft}
            maxLength={80}
            disabled={savingTitle}
            onChange={(event) => onDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Escape") onCancel();
            }}
            className="min-w-0 flex-1 rounded border bg-background px-2 py-1 text-sm"
          />
          <button
            type="submit"
            disabled={savingTitle || !titleDraft.trim()}
            className="text-xs"
          >
            {savingTitle ? "Saving…" : "Save"}
          </button>
          <button
            type="button"
            disabled={savingTitle}
            onClick={() => onCancel()}
            className="text-xs text-muted-foreground"
          >
            Cancel
          </button>
          {renameError && (
            <span role="alert" className="text-xs text-destructive">
              Could not rename. Try again.
            </span>
          )}
        </form>
      ) : (
        <h1
          className="block min-w-0 text-sm font-medium"
          onDoubleClick={() => {
            if (conversation) {
              onRename();
            }
          }}
        >
          <button
            type="button"
            disabled={!conversation}
            className="max-w-full truncate text-left"
            title="Double-click to rename conversation"
            onKeyDown={(event) => {
              if (conversation && ["Enter", " "].includes(event.key)) {
                event.preventDefault();
                onRename();
              }
            }}
          >
            {conversation?.title ?? "Laomedo assistant"}
          </button>
        </h1>
      )}
    </>
  );
}
