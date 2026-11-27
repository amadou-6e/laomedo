import { useEffect, useRef, useState } from "react";
import { Trash2 } from "lucide-react";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { AssistantFailure, assistantRequest } from "../api";

export default function DeleteConversation({ conversation, title, onDeleted, onFailure }: {
  conversation: string;
  title: string;
  onDeleted: () => void;
  onFailure: (error: unknown) => void;
}) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const alive = useRef(false);
  const controller = useRef<AbortController | undefined>(undefined);
  const cancel = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    alive.current = true;
    return () => { alive.current = false; controller.current?.abort(); };
  }, []);

  async function remove() {
    if (busy) return;
    setBusy(true);
    setError("");
    controller.current = new AbortController();
    try {
      await assistantRequest(`/conversations/${encodeURIComponent(conversation)}`, undefined, controller.current.signal, "DELETE");
      if (alive.current) onDeleted();
    } catch (failure) {
      if (!alive.current) return;
      if (failure instanceof AssistantFailure && failure.code === "assistant_conversation_not_found") {
        onDeleted();
      } else if (failure instanceof AssistantFailure && failure.code === "assistant_conversation_active") {
        setError("Wait for the active response or workflow run to finish, then try again.");
      } else {
        setError("Could not confirm deletion. Refresh history before trying again.");
        if (failure instanceof AssistantFailure && failure.code === "assistant_session_locked") onFailure(failure);
      }
    } finally {
      if (alive.current) setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(value) => { if (!busy) { setOpen(value); setError(""); } }}>
      <DialogTrigger asChild>
        <button type="button" aria-label="Delete conversation" title="Delete conversation"
          className="rounded p-1.5 hover:bg-muted hover:text-destructive focus-visible:outline focus-visible:outline-2">
          <Trash2 size={16} />
        </button>
      </DialogTrigger>
      <DialogContent onOpenAutoFocus={(event) => { event.preventDefault(); cancel.current?.focus(); }}>
        <DialogHeader>
          <DialogTitle>Delete conversation?</DialogTitle>
          <DialogDescription>
            Delete “{title}” from Laomedo history? Saved workflows will stay.
          </DialogDescription>
        </DialogHeader>
        {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
        <DialogFooter>
          <button ref={cancel} type="button" disabled={busy} className="rounded-md border px-3 py-2 text-sm disabled:opacity-40" onClick={() => setOpen(false)}>Cancel</button>
          <button type="button" disabled={busy} className="rounded-md bg-destructive px-3 py-2 text-sm text-destructive-foreground disabled:opacity-40" onClick={() => void remove()}>{busy ? "Deleting..." : "Delete"}</button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
