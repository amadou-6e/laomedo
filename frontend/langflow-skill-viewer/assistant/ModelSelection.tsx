import { useId, useRef, useState } from "react";
import { Check, ChevronDown } from "lucide-react";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import type { Models } from "./models";
import { OpenAiIcon } from "@/icons/OpenAi";

export default function ModelSelection({
  models,
  model,
  effort,
  disabled,
  onModel,
  onEffort,
}: {
  models?: Models;
  model: string;
  effort: string;
  disabled: boolean;
  onModel: (value: string) => void;
  onEffort: (value: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const identity = useId();
  const picker = useRef<HTMLDivElement>(null);
  const choices =
    models?.models.find((item) => item.id === model)?.efforts ?? [];
  return (
    <Popover open={open && !disabled} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          disabled={disabled}
          aria-label="Choose model and effort"
          title={model ? `${model} · ${effort}` : "Choose model and effort"}
          className="inline-flex min-w-0 items-center gap-1.5 rounded-full px-2 py-1 text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline focus-visible:outline-2 disabled:opacity-50"
        >
          <span className="max-w-48 truncate text-foreground">
            {model || "Choose model"}
          </span>
          {effort && <span className="capitalize">{effort}</span>}
          <ChevronDown size={12} className="shrink-0" />
        </button>
      </PopoverTrigger>
      <PopoverContent
        ref={picker}
        onOpenAutoFocus={(event) => {
          const selected = picker.current?.querySelector<HTMLInputElement>(
            'input[type="radio"]:checked',
          );
          if (selected) {
            event.preventDefault();
            selected.focus();
          }
        }}
        align="end"
        side="top"
        sideOffset={10}
        className="w-[28rem] max-w-[calc(100vw-2rem)] rounded-2xl p-4"
        aria-label="Model and effort"
      >
        <fieldset aria-label="Assistant model" className="space-y-2">
          <legend className="mb-2 text-xs font-medium text-muted-foreground">
            Find your model
          </legend>
          <p className="mb-3 text-xs text-muted-foreground">
            OpenAI models, powered by Codex
          </p>
          <div className="grid max-h-64 grid-cols-2 gap-2 overflow-y-auto p-0.5">
            {models?.models.map((item) => (
              <label
                key={item.id}
                className={`relative flex min-w-0 cursor-pointer flex-col gap-3 rounded-xl border p-3 text-xs transition-colors hover:border-primary/50 hover:bg-muted has-[:focus-visible]:outline has-[:focus-visible]:outline-2 ${model === item.id ? "border-primary/60 bg-primary/10" : "border-border bg-muted/20"}`}
              >
                <input
                  type="radio"
                  name={`${identity}-model`}
                  aria-label={item.id}
                  value={item.id}
                  checked={model === item.id}
                  onChange={() => onModel(item.id)}
                  className="sr-only"
                />
                <span className="flex items-center justify-between gap-2">
                  <span aria-hidden="true" className="text-2xl">
                    <OpenAiIcon />
                  </span>
                  {model === item.id ? (
                    <span className="inline-flex items-center gap-1 text-[10px] text-primary">
                      <Check size={12} />
                      Selected
                    </span>
                  ) : (
                    <span className="text-[10px] text-muted-foreground">
                      OpenAI
                    </span>
                  )}
                </span>
                <span className="break-words font-medium">{item.id}</span>
              </label>
            ))}
            {!models?.models.length && (
              <p className="px-2 py-2 text-xs text-muted-foreground">
                No models available.
              </p>
            )}
          </div>
          {(models?.models.length ?? 0) > 6 && (
            <p className="pt-2 text-[10px] text-muted-foreground">
              Scroll to explore all {models?.models.length} models.
            </p>
          )}
        </fieldset>
        <fieldset
          aria-label="Assistant reasoning effort"
          className="mt-3 border-t pt-3"
        >
          <legend className="text-xs font-medium text-muted-foreground">
            Reasoning effort
          </legend>
          <div className="mt-3">
            {choices.length > 0 && (
              <>
                <input
                  type="range"
                  aria-label="Reasoning effort"
                  aria-valuetext={effort}
                  min={0}
                  max={Math.max(0, choices.length - 1)}
                  step={1}
                  value={Math.max(0, choices.indexOf(effort))}
                  disabled={choices.length === 1}
                  onChange={(event) =>
                    onEffort(choices[Number(event.target.value)])
                  }
                  className="w-full cursor-pointer accent-primary"
                />
                <div className="mt-1 flex justify-between text-[10px] text-muted-foreground">
                  {choices.map((value) => (
                    <span
                      key={value}
                      className={`capitalize ${effort === value ? "font-medium text-foreground" : ""}`}
                    >
                      {value}
                    </span>
                  ))}
                </div>
              </>
            )}
            {!choices.length && (
              <span className="text-xs text-muted-foreground">
                Choose a model first.
              </span>
            )}
          </div>
        </fieldset>
      </PopoverContent>
    </Popover>
  );
}
