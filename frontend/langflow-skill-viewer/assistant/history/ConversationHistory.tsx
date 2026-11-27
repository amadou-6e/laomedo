import type {
  Dispatch,
  SetStateAction,
  MutableRefObject,
  ReactNode,
} from "react";
import { ChevronLeft, ChevronRight, Loader2, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import ProviderIcon from "../ProviderIcon";
import { stateLabel, type ConversationIndex } from "../models";
import useHistoryPagination from "./useHistoryPagination";
import useHistoryWidth from "./useHistoryWidth";

export default function ConversationHistory({
  index,
  onIndex,
  generation,
  owner,
  selected,
  embedded,
  history,
  historyControl,
  headerActions,
  fail,
  onSelect,
  onNew,
  onToggle,
}: {
  index: ConversationIndex;
  onIndex: Dispatch<SetStateAction<ConversationIndex>>;
  generation: MutableRefObject<number>;
  owner?: string;
  selected: string;
  embedded: boolean;
  history: boolean;
  historyControl: ReactNode;
  headerActions: ReactNode;
  fail: (error: unknown) => void;
  onSelect: (id: string) => void;
  onNew: () => void;
  onToggle: () => void;
}) {
  const { historyList, historySentinel, loadingHistory, olderConversations } =
    useHistoryPagination({
      index,
      onIndex,
      generation,
      owner,
      visible: history,
      fail,
    });
  const {
    panel,
    width,
    maximum,
    drag,
    onPointerDown,
    onPointerMove,
    onPointerUp,
    onKeyDown,
  } = useHistoryWidth(history);
  return (
    <div
      ref={panel}
      style={!embedded && history ? { width, maxWidth: "75vw" } : undefined}
      className={`relative min-h-0 shrink-0 ${history ? (embedded ? "w-full" : "") : embedded ? "hidden" : "w-5"}`}
    >
      <aside
        hidden={!history}
        className={`${history ? "flex" : "hidden"} h-full flex-col bg-muted/20 py-4 pr-2 text-muted-foreground`}
        aria-label="Conversations"
      >
        <div className="mb-4 flex items-center gap-2 px-4">
          <h2 className="flex-1 text-sm font-medium">History</h2>
          {embedded && (
            <>
              {historyControl}
              {headerActions}
            </>
          )}
        </div>
        <nav
          ref={historyList}
          aria-label="Conversation history"
          className="min-h-0 flex-1 divide-y divide-border/20 overflow-y-auto"
          onScroll={(event) => {
            const list = event.currentTarget;
            if (list.scrollHeight - list.scrollTop - list.clientHeight < 100)
              void olderConversations();
          }}
        >
          {index.conversations.map((item) => (
            <button
              key={item.id}
              type="button"
              aria-current={selected === item.id ? "page" : undefined}
              className={`mx-3 flex w-[calc(100%-1.5rem)] items-center gap-2 rounded-lg p-3 text-left text-sm hover:bg-muted hover:text-foreground focus-visible:outline focus-visible:outline-2 ${selected === item.id ? "bg-muted" : ""}`}
              onClick={() => {
                onSelect(item.id);
              }}
            >
              <span className="min-w-0 flex-1">
                <span className="block truncate font-medium">{item.title}</span>
                <span className="mt-1 flex items-center gap-2 text-xs text-muted-foreground">
                  <span className="sr-only">
                    {(
                      {
                        codex: "Codex",
                        claude: "Claude",
                        opencode: "OpenCode",
                      } as Record<string, string>
                    )[item.provider] ?? "Agent"}
                  </span>
                  <ProviderIcon
                    provider={item.provider}
                    monochrome
                    className="h-3 w-3 opacity-70"
                  />
                  <span>
                    {item.active_message_id
                      ? stateLabel(item.state)
                      : new Date(item.updated_at * 1000).toLocaleDateString()}
                  </span>
                </span>
              </span>
              {item.active_message_id && (
                <Loader2
                  size={12}
                  className="shrink-0 animate-spin text-muted-foreground"
                  aria-label="Conversation working"
                />
              )}
            </button>
          ))}
          <div ref={historySentinel} aria-hidden="true" />
          {loadingHistory && (
            <p
              role="status"
              className="flex justify-center py-3 text-muted-foreground"
            >
              <Loader2 size={14} className="animate-spin" aria-hidden="true" />
              <span className="sr-only">Loading earlier conversations</span>
            </p>
          )}
        </nav>
        {index.conversations.some(
          (item) => item.id !== selected && item.active_message_id,
        ) && (
          <p
            role="status"
            className="mt-3 flex items-center gap-2 text-xs text-muted-foreground"
          >
            <Loader2 size={12} className="animate-spin" aria-hidden="true" />
            Working in background
          </p>
        )}
        <Button
          className="mx-3 mt-4 w-[calc(100%-1.5rem)] justify-start text-muted-foreground hover:text-foreground"
          variant="ghost"
          aria-label="New conversation"
          onClick={onNew}
        >
          <Plus size={16} />
          New conversation
        </Button>
      </aside>
      {!embedded && (
        <div
          role="separator"
          aria-label="Resize history"
          aria-orientation="vertical"
          aria-valuemin={180}
          aria-valuemax={maximum}
          aria-valuenow={history ? width : 20}
          tabIndex={0}
          className="absolute inset-y-0 right-0 z-10 w-2 touch-none border-r text-muted-foreground hover:bg-muted focus-visible:outline focus-visible:outline-2"
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onKeyDown={onKeyDown}
        >
          <button
            type="button"
            aria-label={
              history ? "Collapse conversations" : "Expand conversations"
            }
            title="Drag to resize; click to toggle history"
            aria-expanded={history}
            onClick={(event) => {
              if (event.detail !== 0 && drag.current.moved) {
                drag.current.moved = false;
                return;
              }
              onToggle();
            }}
            className={`flex h-full w-full items-center justify-center hover:text-foreground focus-visible:outline focus-visible:outline-2 ${history ? "cursor-col-resize" : "cursor-pointer"}`}
          >
            {history ? <ChevronLeft size={12} /> : <ChevronRight size={12} />}
          </button>
        </div>
      )}
    </div>
  );
}
