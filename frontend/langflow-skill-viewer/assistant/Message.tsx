import { useEffect, useState } from "react";
import {
  MessageMarkdown,
} from "@/modals/graphAgents/components";
import type { Lane } from "@/modals/graphAgents/models";
import ToolCalls from "./ToolCalls";
import { messageText } from "@/modals/graphAgents/utils";
import { AssistantFailure, assistantRequest } from "./api";
import ErrorExplanation from "@/components/laomedoErrors/ErrorExplanation";
import { describeNodeFailure } from "@/components/laomedoErrors/nodeErrors";
import type { ActivityPage, DraftReceipt, Message } from "./models";
import { stateLabel } from "./models";
import Thinking from "./Thinking";
import CopyAnswer from "./CopyAnswer";
import { responseTranscript, hasNativeCommandOutcome, hasNativeControlResult, nativeResponseText } from "./responseTranscript";
import GraphActions from "./GraphActions";
import NativeActions from "./NativeActions";
import NativeStatus from "./NativeStatus";
import type { GraphAction, NativeAction } from "./models";

export function UserMessage({
  text,
  createdAt,
  command = /^\/[a-z][a-z0-9_-]*(?:\s|$)/i.test(text),
}: {
  text: string;
  createdAt?: number;
  command?: boolean;
}) {
  return (
    <div className="ml-auto max-w-[90%] space-y-2 md:max-w-[80%]">
      <p className="text-right text-xs text-muted-foreground">
        {createdAt
          ? new Date(createdAt * 1000).toLocaleTimeString([], {
              hour: "2-digit",
              minute: "2-digit",
            })
          : "\u00a0"}
      </p>
      <div className={command ? "text-right text-muted-foreground" : "ml-auto w-fit max-w-full rounded-xl rounded-tr-sm border bg-muted/50 px-4 py-3"}>
        <p className="whitespace-pre-wrap break-words text-sm leading-[1.7142857]">
          {text}
        </p>
      </div>
    </div>
  );
}

export default function MessageRow({
  conversation,
  provider = "codex",
  message,
  receipts,
  active,
  onContent,
  onFailure,
  actions = [],
  nativeActions = [],
  errorShownAbove = false,
}: {
  conversation: string;
  provider?: string;
  actions?: GraphAction[];
  nativeActions?: NativeAction[];
  errorShownAbove?: boolean;
  message: Message;
  receipts: DraftReceipt[];
  active: boolean;
  onContent: () => void;
  onFailure: (error: unknown) => void;
}) {
  const [page, setPage] = useState<ActivityPage>();
  const nativeControl = hasNativeControlResult(message, provider);
  useEffect(() => {
    if (nativeControl) return;
    const controller = new AbortController();
    let busy = false;
    const refresh = async () => {
      if (busy) return;
      busy = true;
      try {
        const result = await assistantRequest<ActivityPage>(
          `/conversations/${conversation}/activity?attempt=${message.attempt_id}&after=0`,
          undefined,
          controller.signal,
        );
        if (!controller.signal.aborted) {
          setPage(result);
          requestAnimationFrame(onContent);
        }
      } catch (failure) {
        if (
          !controller.signal.aborted &&
          failure instanceof AssistantFailure &&
          failure.code === "assistant_session_locked"
        )
          onFailure(failure);
      } finally {
        busy = false;
      }
    };
    void refresh();
    const timer = active ? window.setInterval(refresh, 800) : undefined;
    return () => {
      controller.abort();
      if (timer) window.clearInterval(timer);
    };
  }, [
    conversation,
    message.attempt_id,
    message.state,
    active,
    onContent,
    onFailure,
    nativeControl,
  ]);
  const items = (nativeControl ? [] : page?.projection?.items ?? []).filter(
    (lane) => lane.item?.type !== "userMessage",
  );
  const nativeStatus = Boolean(provider === "codex" && (message.native_action_id || message.initial_native_command === "status") && message.text === "/status" && message.state === "completed" && message.response);
  const hasAnswer = items.some(
    (lane) => messageText(lane.item ?? {}, provider) !== null,
  );
  const groups: Lane[][] = [];
  for (const lane of items) {
    const previous = groups[groups.length - 1];
    if (
      messageText(lane.item ?? {}, provider) === null &&
      previous &&
      messageText(previous[0].item ?? {}, provider) === null
    )
      previous.push(lane);
    else groups.push([lane]);
  }
  return (
    <section className="space-y-5" aria-label="Message and response">
      <UserMessage text={message.text} createdAt={message.created_at} command={Boolean(message.native_action_id || message.initial_native_command)} />
      {nativeStatus ? <NativeStatus text={message.response!} conversation={conversation} /> : groups.map((group) => {
        const lane = group[0];
        const text = messageText(lane.item ?? {}, provider);
        return text !== null ? (
          <div key={`${lane.thread}:${lane.id}`} className="space-y-2">
            <MessageMarkdown text={text} allowLinks={false} />
          </div>
        ) : (
          <ToolCalls
            key={`${lane.thread}:${lane.id}`}
            lanes={group}
            names={page?.tool_names ?? {}}
            compactionCompleted={Boolean(message.native_action_id && message.text === "/compact" && message.state === "completed")}
          />
        );
      })}
      {!nativeStatus && !hasAnswer && message.response && (
        <div className="space-y-2" aria-label={nativeControl ? "Native command output" : undefined}>
          <MessageMarkdown text={nativeResponseText(message, provider)!} allowLinks={false} />
        </div>
      )}
      {active && ["reserved", "starting", "running"].includes(message.state) ? (
        !hasAnswer && !message.response ? (
          <Thinking />
        ) : null
      ) : active ? (
        <p
          role="status"
          aria-live="polite"
          className="text-sm text-muted-foreground"
        >
          {stateLabel(message.state)}…
        </p>
      ) : null}
      {!active &&
        ["cancelled", "failed", "interrupted"].includes(message.state) && (
          <p className="text-sm text-muted-foreground">
            {stateLabel(message.state)}. Retained messages and saved drafts are
            preserved.
          </p>
        )}
      {message.error_code && !errorShownAbove && (
        <div className="rounded-lg border p-3 text-sm">
          <ErrorExplanation
            failure={describeNodeFailure(message.error_code, undefined)}
          />
        </div>
      )}
      {page?.complete === false && !hasNativeCommandOutcome(message, provider) && (
        <p className="text-xs text-muted-foreground">
          Some Activity could not be retained. The response above may be
          partial.
        </p>
      )}
      <GraphActions
        conversation={conversation}
        actions={actions}
        onFailure={onFailure}
      />
      <NativeActions conversation={conversation} provider={provider} actions={nativeActions} onFailure={onFailure} />
      {receipts.map((receipt) => (
        <article
          key={receipt.id}
          className="rounded-xl border bg-muted/30 p-4"
          aria-label={`Saved draft: ${receipt.name}`}
        >
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h3 className="text-sm font-semibold">
                Saved draft: {receipt.name}
              </h3>
              <p
                className="mt-1 text-xs text-muted-foreground"
                title={receipt.revision}
              >
                Saved revision {receipt.revision.slice(7, 19)} ·{" "}
                {receipt.diagnostics.length
                  ? "Incomplete draft"
                  : "Structural checks passed"}
              </p>
            </div>
            <a
              className="inline-flex rounded-md border bg-background px-3 py-2 text-sm font-medium hover:bg-muted focus-visible:outline focus-visible:outline-2"
              href={`/flow/${encodeURIComponent(receipt.workflow_id)}`}
              target="_blank"
              rel="noopener noreferrer"
            >
              Open draft in new tab ↗
            </a>
          </div>
          {receipt.diagnostics.length > 0 && (
            <details className="mt-3 text-xs text-muted-foreground">
              <summary className="cursor-pointer">
                Settings to finish in the editor ({receipt.diagnostics.length})
              </summary>
              <ul className="mt-2 list-disc space-y-1 pl-5">
                {receipt.diagnostics.map((item, index) => (
                  <li key={index}>{item}</li>
                ))}
              </ul>
            </details>
          )}
          <p className="mt-3 text-xs text-muted-foreground">
            Saved without running or publishing. Opening is your choice; current
            editor work stays in its tab.
          </p>
        </article>
      ))}
      {(items.length > 0 || message.response || receipts.length > 0 || actions.length > 0 || nativeActions.length > 0) && (
        <CopyAnswer disabled={!page && !hasNativeCommandOutcome(message, provider)} text={responseTranscript(page, message, receipts, actions, nativeActions, provider)} />
      )}
    </section>
  );
}
