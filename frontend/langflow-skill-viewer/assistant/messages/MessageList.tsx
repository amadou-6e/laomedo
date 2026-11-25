import MessageRow, { UserMessage } from "./Message";
import Thinking from "./Thinking";
import type { ConversationDetail, PendingSubmission } from "../models";

export default function MessageList({
  conversationId,
  provider,
  detail,
  activeMessageId,
  failureShown,
  explanation,
  waiting,
  retryable,
  busy,
  active,
  loading,
  onContent,
  onFailure,
  onRetry,
}: {
  conversationId: string;
  provider: string;
  detail?: ConversationDetail;
  activeMessageId?: string | null;
  failureShown: boolean;
  explanation?: string | null;
  waiting?: PendingSubmission;
  retryable: boolean;
  busy: boolean;
  active: boolean;
  loading: boolean;
  onContent: () => void;
  onFailure: (error: unknown) => void;
  onRetry: (submission: PendingSubmission) => void;
}) {
  return (
    <>
      {detail?.messages.map((message) => (
        <MessageRow
          key={message.id}
          conversation={conversationId}
          provider={provider}
          message={message}
          actions={(detail.actions ?? []).filter(
            (action) => action.message_id === message.id,
          )}
          nativeActions={(detail.native_actions ?? []).filter(
            (action) => action.message_id === message.id,
          )}
          receipts={detail.drafts.filter(
            (receipt) => receipt.message_id === message.id,
          )}
          active={activeMessageId === message.id}
          errorShownAbove={Boolean(
            failureShown &&
              message.error_code === explanation &&
              message.id ===
                (activeMessageId ??
                  detail.messages[detail.messages.length - 1]?.id),
          )}
          onContent={onContent}
          onFailure={onFailure}
        />
      ))}
      {waiting &&
        !detail?.messages.some(
          (row) => row.client_message_id === waiting.id,
        ) && (
          <section className="space-y-5 pb-6" aria-label="Message and response">
            <UserMessage text={waiting.text} />
            {retryable && !busy && !loading ? (
              <div>
                <button
                  type="button"
                  disabled={busy || active}
                  className="mt-3 text-sm underline"
                  onClick={() => onRetry(waiting)}
                >
                  Retry same submission
                </button>
                <p className="mt-1 text-xs text-muted-foreground">
                  Reuses its original message ID. Accepted messages are observed
                  rather than dispatched again.
                </p>
              </div>
            ) : (
              <Thinking />
            )}
          </section>
        )}
    </>
  );
}
