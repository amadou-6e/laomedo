import type { ComponentProps } from "react";
import { ArrowUp, Square } from "lucide-react";
import AccountSelection from "./AccountSelection";
import ModelSelection from "./ModelSelection";
import NativeCommandMenu from "../commands/NativeCommandMenu";

export default function Composer({
  selected,
  provider,
  runId,
  threadId,
  active,
  stopping,
  busy,
  text,
  readOnly,
  canSubmit,
  commandsDismissed,
  accountsLoading,
  hasAccounts,
  hasConnection,
  composerStatus,
  accountSelection,
  modelSelection,
  onDraft,
  onDismissCommands,
  onSend,
  onStop,
}: {
  selected: string;
  provider: string;
  runId?: string | null;
  threadId?: string | null;
  active: boolean;
  stopping: boolean;
  busy: boolean;
  text: string;
  readOnly: boolean;
  canSubmit: boolean;
  commandsDismissed: boolean;
  accountsLoading: boolean;
  hasAccounts: boolean;
  hasConnection: boolean;
  composerStatus?: string;
  accountSelection: ComponentProps<typeof AccountSelection>;
  modelSelection: ComponentProps<typeof ModelSelection>;
  onDraft: (text: string) => void;
  onDismissCommands: (dismissed: boolean) => void;
  onSend: () => void;
  onStop: () => void;
}) {
  return (
    <form
      className="shrink-0 bg-background px-4 pb-4 pt-2 md:px-10"
      onSubmit={(event) => {
        event.preventDefault();
        onSend();
      }}
    >
      <div className="relative mx-auto max-w-4xl rounded-2xl border bg-muted/30 p-2 shadow-sm focus-within:ring-1 focus-within:ring-ring">
        {!commandsDismissed &&
          (provider === "codex" ? /^[/$][^\s]*$/ : /^\/[^\s]*$/).test(text) && (
            <NativeCommandMenu
              conversation={selected}
              provider={provider}
              runId={runId}
              threadId={threadId}
              active={active}
              text={text}
              onSelect={(text) => {
                onDraft(text);
                document.getElementById("assistant-message")?.focus();
              }}
              onClose={() => {
                onDismissCommands(true);
                document.getElementById("assistant-message")?.focus();
              }}
            />
          )}
        <label htmlFor="assistant-message" className="sr-only">
          Message this assistant
        </label>
        <textarea
          id="assistant-message"
          maxLength={12000}
          rows={2}
          placeholder={
            selected
              ? "Message this assistant…"
              : accountsLoading
                ? "Loading accounts…"
                : !hasConnection
                  ? hasAccounts
                    ? "Select an account"
                    : "No account available"
                  : "Start chat…"
          }
          value={text}
          readOnly={readOnly}
          onChange={(event) => {
            onDraft(event.target.value);
            onDismissCommands(false);
          }}
          onKeyDown={(event) => {
            if (event.key === "Escape") onDismissCommands(true);
            if (
              event.key === "ArrowDown" &&
              document.getElementById("assistant-native-commands")
            ) {
              event.preventDefault();
              document
                .querySelector<HTMLButtonElement>(
                  "#assistant-native-commands button:not(:disabled)",
                )
                ?.focus();
              return;
            }
            if (
              event.key === "Enter" &&
              !event.shiftKey &&
              !event.nativeEvent.isComposing
            ) {
              event.preventDefault();
              if (
                document.querySelector(
                  '#assistant-native-commands [role="status"]',
                )
              )
                return;
              const first = document.querySelector<HTMLButtonElement>(
                "#assistant-native-commands button:not(:disabled):not([data-command-retry])",
              );
              if (first) {
                first.click();
                return;
              }
              onSend();
            }
          }}
          className="block w-full resize-none border-0 bg-transparent px-2 py-2 text-sm outline-none placeholder:text-muted-foreground read-only:opacity-60"
        />
        {composerStatus && (
          <p
            id="assistant-composer-status"
            role="status"
            className="px-2 pb-1 text-xs text-muted-foreground"
          >
            {composerStatus}
            {!accountsLoading && !hasAccounts && (
              <>
                {" "}
                <a
                  href="/settings/providers"
                  onClick={(event) => {
                    if (!accountSelection.onManageAccounts?.())
                      event.preventDefault();
                  }}
                  className="underline underline-offset-2"
                >
                  Connect account
                </a>
              </>
            )}
          </p>
        )}
        <div className="mt-1 flex items-center justify-end gap-2 px-1">
          <AccountSelection {...accountSelection} />
          <ModelSelection {...modelSelection} />
          {active ? (
            <button
              type="button"
              aria-label="Stop response"
              title={stopping ? "Stopping…" : "Stop response"}
              disabled={busy || stopping}
              onClick={onStop}
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-foreground text-background disabled:opacity-40"
            >
              <Square size={12} fill="currentColor" />
            </button>
          ) : (
            <button
              type="submit"
              aria-label={selected ? "Send" : "Start chat"}
              title={
                composerStatus ??
                (selected ? "Send (Enter)" : "Start chat (Enter)")
              }
              aria-describedby={
                composerStatus ? "assistant-composer-status" : undefined
              }
              disabled={!canSubmit || !text.trim()}
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-foreground text-background transition-opacity disabled:opacity-30"
            >
              <ArrowUp size={17} />
            </button>
          )}
        </div>
      </div>
    </form>
  );
}
