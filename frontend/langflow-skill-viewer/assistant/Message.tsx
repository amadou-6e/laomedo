import { useEffect, useState } from "react";
import Markdown from "react-markdown";
import type { Lane } from "@/modals/graphAgents/models";
import ToolCalls from "./ToolCalls";
import { messageText } from "@/modals/graphAgents/utils";
import { AssistantFailure, assistantRequest } from "./api";
import ErrorExplanation from "@/components/laomedoErrors/ErrorExplanation";
import { describeNodeFailure } from "@/components/laomedoErrors/nodeErrors";
import type { ActivityPage, DraftReceipt, Message } from "./models";
import { stateLabel } from "./models";

export function AssistantText({ text }: { text: string }) {
  return (
    <Markdown
      skipHtml
      disallowedElements={["img", "a"]}
      unwrapDisallowed
      className="prose prose-sm max-w-none break-words dark:prose-invert [&_pre]:overflow-x-auto [&_pre]:whitespace-pre-wrap [&_code]:break-words prose-code:before:content-none prose-code:after:content-none"
    >
      {text}
    </Markdown>
  );
}

export default function MessageRow({
  conversation,
  message,
  receipts,
  active,
  onContent,
  onFailure,
}: {
  conversation: string;
  message: Message;
  receipts: DraftReceipt[];
  active: boolean;
  onContent: () => void;
  onFailure: (error: unknown) => void;
}) {
  const [page, setPage] = useState<ActivityPage>();
  useEffect(() => {
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
  ]);
  const items = (page?.projection?.items ?? []).filter(
    (lane) => lane.item?.type !== "userMessage",
  );
  const hasAnswer = items.some(
    (lane) => messageText(lane.item ?? {}, "codex") !== null,
  );
  const groups: Lane[][] = [];
  for (const lane of items) {
    const previous = groups[groups.length - 1];
    if (
      messageText(lane.item ?? {}, "codex") === null &&
      previous &&
      messageText(previous[0].item ?? {}, "codex") === null
    )
      previous.push(lane);
    else groups.push([lane]);
  }
  return (
    <section className="space-y-5 pb-6" aria-label="Message and response">
      <div className="ml-auto max-w-[90%] space-y-2 md:max-w-[80%]">
        <p className="text-right text-xs text-muted-foreground">
          {new Date(message.created_at * 1000).toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
          })}
        </p>
        <div className="rounded-xl rounded-tr-sm border bg-muted/50 px-4 py-3">
          <p className="whitespace-pre-wrap break-words text-sm leading-[1.7142857]">
            {message.text}
          </p>
        </div>
      </div>
      {groups.map((group) => {
        const lane = group[0];
        const text = messageText(lane.item ?? {}, "codex");
        return text !== null ? (
          <div key={`${lane.thread}:${lane.id}`} className="space-y-2">
            <AssistantText text={text} />
          </div>
        ) : (
          <ToolCalls
            key={`${lane.thread}:${lane.id}`}
            lanes={group}
            names={page?.tool_names ?? {}}
          />
        );
      })}
      {!hasAnswer && message.response && (
        <div className="space-y-2">
          <AssistantText text={message.response} />
        </div>
      )}
      {active && (
        <p
          role="status"
          aria-live="polite"
          className="text-sm text-muted-foreground"
        >
          {stateLabel(message.state)}…
        </p>
      )}
      {!active &&
        ["cancelled", "failed", "interrupted"].includes(message.state) && (
          <p className="text-sm text-muted-foreground">
            {stateLabel(message.state)}. Retained messages and saved drafts are
            preserved.
          </p>
        )}
      {message.error_code && (
        <div className="rounded-lg border p-3 text-sm">
          <ErrorExplanation
            failure={describeNodeFailure(message.error_code, undefined)}
          />
        </div>
      )}
      {page?.complete === false && (
        <p className="text-xs text-muted-foreground">
          Some Activity could not be retained. The response above may be
          partial.
        </p>
      )}
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
    </section>
  );
}
