import { useId, useState } from "react";
import { Check, ChevronDown, RefreshCw } from "lucide-react";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import type { Models } from "./models";

export default function ModelSelection({
  models,
  model,
  effort,
  disabled,
  onModel,
  onEffort,
  onRefresh,
}: {
  models?: Models;
  model: string;
  effort: string;
  disabled: boolean;
  onModel: (value: string) => void;
  onEffort: (value: string) => void;
  onRefresh: () => void;
}) {
  const [open, setOpen] = useState(false);
  const identity = useId();
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
        align="end"
        side="top"
        sideOffset={10}
        className="w-72 max-w-[calc(100vw-2rem)] rounded-xl p-3"
        aria-label="Model and effort"
      >
        <fieldset aria-label="Assistant model" className="space-y-2">
          <legend className="mb-2 text-xs font-medium text-muted-foreground">
            Model
          </legend>
          <div className="max-h-52 overflow-y-auto">
            {models?.models.map((item) => (
              <label
                key={item.id}
                className={`flex cursor-pointer items-center justify-between gap-2 rounded-md px-2 py-2 text-xs hover:bg-muted has-[:focus-visible]:outline has-[:focus-visible]:outline-2 ${model === item.id ? "bg-muted" : ""}`}
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
                <span className="truncate">{item.id}</span>
                {model === item.id && <Check size={12} className="shrink-0" />}
              </label>
            ))}
            {!models?.models.length && (
              <p className="px-2 py-2 text-xs text-muted-foreground">
                No models available. Refresh to check again.
              </p>
            )}
          </div>
        </fieldset>
        <fieldset
          aria-label="Assistant reasoning effort"
          className="mt-3 border-t pt-3"
        >
          <legend className="text-xs font-medium text-muted-foreground">
            Reasoning effort
          </legend>
          <div className="mt-2 flex flex-wrap gap-1">
            {choices.map((value) => (
              <label
                key={value}
                className={`cursor-pointer rounded-md px-2 py-1.5 text-xs capitalize hover:bg-muted has-[:focus-visible]:outline has-[:focus-visible]:outline-2 ${effort === value ? "bg-muted text-foreground" : "text-muted-foreground"}`}
              >
                <input
                  type="radio"
                  name={`${identity}-effort`}
                  aria-label={value}
                  value={value}
                  checked={effort === value}
                  className="sr-only"
                  onChange={() => {
                    onEffort(value);
                    setOpen(false);
                  }}
                />
                {value}
              </label>
            ))}
            {!choices.length && (
              <span className="text-xs text-muted-foreground">
                Choose a model first.
              </span>
            )}
          </div>
        </fieldset>
        <button
          type="button"
          onClick={onRefresh}
          className="mt-3 inline-flex items-center gap-1.5 rounded px-2 py-1 text-xs text-muted-foreground hover:bg-muted"
        >
          <RefreshCw size={12} />
          Refresh models
        </button>
      </PopoverContent>
    </Popover>
  );
}
