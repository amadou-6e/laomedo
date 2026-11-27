import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type MutableRefObject,
} from "react";
import { assistantRequest } from "../api";
import type { ConversationDetail, ConversationIndex, Models } from "../models";

export default function useModelDiscovery({
  selected,
  locked,
  providerKnown,
  chosenProvider,
  connectionId,
  connectionGeneration,
  binding,
  generation,
  bindingRef,
  fail,
  clearError,
  detail,
  index,
}: {
  selected: string;
  locked: boolean;
  providerKnown: boolean;
  chosenProvider: string;
  connectionId?: string | null;
  connectionGeneration?: number | null;
  binding: string;
  generation: MutableRefObject<number>;
  bindingRef: MutableRefObject<string>;
  fail: (error: unknown) => void;
  clearError: () => void;
  detail?: ConversationDetail;
  index: ConversationIndex;
}) {
  const [models, setModels] = useState<Models>();
  const [model, setModel] = useState("");
  const [effort, setEffort] = useState("");
  const [discovering, setDiscovering] = useState(false);
  const discover = useCallback(async () => {
    if (!providerKnown || !connectionId || !connectionGeneration) {
      setModels(undefined);
      setDiscovering(false);
      return;
    }
    const epoch = generation.current;
    const expectedBinding = binding;
    setDiscovering(true);
    setModels(undefined);
    clearError();
    try {
      const result = await assistantRequest<Models>(
        `/models?provider=${encodeURIComponent(chosenProvider)}&connection_id=${encodeURIComponent(connectionId)}&connection_generation=${connectionGeneration}`,
      );
      if (
        epoch === generation.current &&
        bindingRef.current === expectedBinding
      )
        setModels(result);
    } catch (failure) {
      if (
        epoch === generation.current &&
        bindingRef.current === expectedBinding
      )
        fail(failure);
    } finally {
      if (
        epoch === generation.current &&
        bindingRef.current === expectedBinding
      )
        setDiscovering(false);
    }
  }, [
    fail,
    chosenProvider,
    providerKnown,
    connectionId,
    connectionGeneration,
    binding,
  ]);

  useEffect(() => {
    if (!locked) void discover();
  }, [selected, locked, discover]);

  const boundSelection = useRef("");
  useEffect(() => {
    if (!selected) {
      boundSelection.current = "";
    } else if (
      detail?.conversation.id === selected &&
      boundSelection.current !== selected
    ) {
      boundSelection.current = selected;
      setModel(detail.conversation.model);
      setEffort(detail.conversation.effort);
    }
  }, [selected, detail?.conversation.id]);

  useEffect(() => {
    if (selected || !models) return;
    const recent = index.conversations.find((conversation) =>
      models.models.some(
        (choice) =>
          choice.id === conversation.model &&
          choice.efforts.includes(conversation.effort),
      ),
    );
    const choice =
      models.models.find((item) => item.id === model && item.efforts.length) ??
      models.models.find((item) => item.id === recent?.model) ??
      models.models.find((item) => item.efforts.length);
    if (!choice) return;
    setModel(choice.id);
    setEffort(
      choice.efforts.includes(effort)
        ? effort
        : recent && choice.id === recent.model
          ? recent.effort
          : choice.efforts[0],
    );
  }, [selected, models, model, effort, index.conversations]);

  return {
    models,
    setModels,
    model,
    setModel,
    effort,
    setEffort,
    discovering,
    boundSelection,
  };
}
