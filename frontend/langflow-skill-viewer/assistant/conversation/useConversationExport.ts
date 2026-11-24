import { useEffect, useRef, useState, type MutableRefObject } from "react";
import { AssistantFailure } from "../api";
import { conversationTranscript, downloadTranscript } from "./transcript";

export default function useConversationExport({
  selected,
  owner,
  locked,
  generation,
  currentSelection,
  fail,
}: {
  selected: string;
  owner?: string;
  locked: boolean;
  generation: MutableRefObject<number>;
  currentSelection: MutableRefObject<string>;
  fail: (error: unknown) => void;
}) {
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState(false);
  const exportController = useRef<AbortController | undefined>(undefined);
  useEffect(() => {
    setExporting(false);
    setExportError(false);
    return () => exportController.current?.abort();
  }, [selected, owner, locked]);

  async function exportConversation() {
    if (!selected || exporting || locked) return;
    const controller = new AbortController();
    exportController.current = controller;
    const epoch = generation.current,
      identity = selected;
    setExporting(true);
    setExportError(false);
    try {
      const result = await conversationTranscript(identity, controller.signal);
      if (
        !controller.signal.aborted &&
        epoch === generation.current &&
        currentSelection.current === identity
      )
        downloadTranscript(result.text, result.filename);
    } catch (failure) {
      if (
        !controller.signal.aborted &&
        epoch === generation.current &&
        currentSelection.current === identity
      ) {
        setExportError(true);
        if (
          failure instanceof AssistantFailure &&
          failure.code === "assistant_session_locked"
        )
          fail(failure);
      }
    } finally {
      if (exportController.current === controller) setExporting(false);
    }
  }

  return { exporting, exportError, exportConversation, exportController };
}
