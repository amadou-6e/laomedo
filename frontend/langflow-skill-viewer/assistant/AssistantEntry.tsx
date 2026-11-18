import { useEffect, useState } from "react";
import { useMatch } from "react-router-dom";
import IconComponent from "@/components/common/genericIconComponent";
import useAuthStore from "@/stores/authStore";
import { assistantRequest } from "./api";
import type { ConversationIndex } from "./models";
import { useAssistantSidebarStore } from "./sidebarStore";

export default function AssistantEntry() {
  const graph = useMatch("/flow/:id");
  const { open, setOpen } = useAssistantSidebarStore();
  const owner = useAuthStore((state) => state.userData?.id);
  const [active, setActive] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    setActive(false);
    if (!owner) return () => controller.abort();
    const refresh = async () => {
      if (document.hidden) return;
      try {
        const result = await assistantRequest<ConversationIndex>(
          "/conversations",
          undefined,
          controller.signal,
        );
        if (!controller.signal.aborted)
          setActive(
            result.conversations.some((item) => item.active_message_id),
          );
      } catch {
        if (!controller.signal.aborted) setActive(false);
      }
    };
    void refresh();
    const timer = window.setInterval(refresh, 4000);
    return () => {
      controller.abort();
      window.clearInterval(timer);
    };
  }, [owner]);
  if (graph) return (
    <button type="button" aria-label={open ? "Close assistant sidebar" : "Open assistant sidebar"} aria-expanded={open} aria-controls="laomedo-assistant-sidebar"
      onClick={() => setOpen(!open)}
      className="relative inline-flex items-center gap-2 rounded-md px-2 py-2 text-sm text-muted-foreground hover:bg-muted hover:text-foreground focus-visible:outline focus-visible:outline-2">
      <IconComponent name="MessageSquare" className="h-4 w-4" /><span>Assistant</span>
      {active && <span aria-hidden="true" className="h-2 w-2 rounded-full bg-primary" />}
    </button>
  );
  return (
    <a
      href="/assistant"
      target="_blank"
      rel="noopener noreferrer"
      className="relative inline-flex items-center gap-2 rounded-md px-2 py-2 text-sm text-muted-foreground hover:bg-muted hover:text-foreground focus-visible:outline focus-visible:outline-2"
      title="Open assistant in a new tab"
      aria-label={
        active
          ? "Assistant — activity in another conversation"
          : "Open assistant in a new tab"
      }
    >
      <IconComponent name="MessageSquare" className="h-4 w-4" />
      <span>Assistant</span>
      {active && (
        <span aria-hidden="true" className="h-2 w-2 rounded-full bg-primary" />
      )}
    </a>
  );
}
