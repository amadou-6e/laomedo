import { MessageSquare } from "lucide-react";
import { useAssistantSidebarStore } from "./sidebarStore";

export default function AssistantSidebarToggle({hiddenFromTabOrder = false}: {hiddenFromTabOrder?: boolean}) {
  const {open, setOpen} = useAssistantSidebarStore();
  return <li className="px-1 pt-1">
    <button id="laomedo-assistant-opener" type="button"
      aria-label={open ? "Close assistant sidebar" : "Open assistant sidebar"}
      title="Assistant" aria-expanded={open} aria-controls="laomedo-assistant-sidebar"
      tabIndex={hiddenFromTabOrder ? -1 : undefined}
      onClick={() => setOpen(!open)}
      className={`flex h-8 w-8 items-center justify-center rounded-md p-0 focus-visible:outline focus-visible:outline-2 ${open ? "bg-accent text-accent-foreground" : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"}`}>
      <MessageSquare aria-hidden="true" className="h-5 w-5" />
    </button>
  </li>;
}
