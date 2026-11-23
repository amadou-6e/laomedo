import {
  useEffect,
  useRef,
  useState,
  type Dispatch,
  type SetStateAction,
  type MutableRefObject,
} from "react";
import { assistantRequest } from "../api";
import type { ConversationIndex } from "../models";

export default function useHistoryPagination({
  index,
  onIndex,
  generation,
  owner,
  visible,
  fail,
}: {
  index: ConversationIndex;
  onIndex: Dispatch<SetStateAction<ConversationIndex>>;
  generation: MutableRefObject<number>;
  owner?: string;
  visible: boolean;
  fail: (error: unknown) => void;
}) {
  const [loadingHistory, setLoadingHistory] = useState(false);
  const historyLoading = useRef<symbol | undefined>(undefined);
  const historyList = useRef<HTMLElement>(null);
  const historySentinel = useRef<HTMLDivElement>(null);
  useEffect(() => {
    historyLoading.current = undefined;
    setLoadingHistory(false);
  }, [owner]);
  async function olderConversations() {
    if (index.next_cursor === null || historyLoading.current) return;
    const request = Symbol();
    historyLoading.current = request;
    setLoadingHistory(true);
    const epoch = generation.current;
    try {
      const page = await assistantRequest<ConversationIndex>(
        `/conversations?cursor=${index.next_cursor}`,
      );
      if (epoch !== generation.current) return;
      onIndex((current) => ({
        ...page,
        conversations: [
          ...current.conversations,
          ...page.conversations.filter(
            (row) =>
              !current.conversations.some((existing) => existing.id === row.id),
          ),
        ],
      }));
    } catch (failure) {
      if (epoch === generation.current) fail(failure);
    } finally {
      if (historyLoading.current === request) {
        historyLoading.current = undefined;
        setLoadingHistory(false);
      }
    }
  }

  useEffect(() => {
    const target = historySentinel.current;
    if (
      !visible ||
      index.next_cursor === null ||
      !target ||
      typeof IntersectionObserver === "undefined"
    )
      return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting))
          void olderConversations();
      },
      { root: historyList.current, rootMargin: "100px" },
    );
    observer.observe(target);
    return () => observer.disconnect();
  }, [visible, index.next_cursor, index.conversations.length, owner]);

  return { historyList, historySentinel, loadingHistory, olderConversations };
}
