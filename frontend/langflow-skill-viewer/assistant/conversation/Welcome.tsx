import { Check, MessageSquare, Sparkles, Workflow } from "lucide-react";
import ProviderIcon from "../ProviderIcon";

export default function Welcome({
  selected,
  linked,
  provider,
  pending,
  onProvider,
}: {
  selected: string;
  linked: string;
  provider: string;
  pending: boolean;
  onProvider: (provider: string) => void;
}) {
  return (
    <div className="mx-auto w-full max-w-md space-y-5 py-10 text-center">
      <div
        aria-hidden="true"
        className="relative mx-auto flex h-24 w-64 items-center justify-center gap-4 rounded-full bg-gradient-to-r from-transparent via-primary/10 to-transparent"
      >
        <span className="-rotate-6 rounded-2xl border bg-background p-3 text-muted-foreground shadow-sm">
          <MessageSquare size={22} />
        </span>
        <span className="h-px w-5 bg-primary/40" />
        <span className="relative rounded-2xl border border-primary/30 bg-primary/10 p-4 text-primary shadow-sm">
          <Workflow size={32} />
          <Sparkles size={15} className="absolute -right-2 -top-2" />
        </span>
        <span className="h-px w-5 bg-primary/40" />
        <span className="rotate-6 rounded-2xl border bg-background p-3 text-muted-foreground shadow-sm">
          <Check size={22} />
        </span>
      </div>
      <h2 className="text-xl font-medium">What would you like to build?</h2>
      <p className="mx-auto w-full max-w-sm text-sm text-muted-foreground">
        Describe a workflow or ask me to change one. I can inspect workflows and
        save a separate editable draft.
      </p>
      {!selected && (
        <fieldset
          className="mx-auto w-full max-w-xs pt-2 text-left"
          aria-label="Assistant provider"
        >
          {[
            ["codex", "Codex", "OpenAI"],
            ["claude", "Claude", "Anthropic"],
            ["opencode", "OpenCode", "Connected models"],
          ].map(([id, name, description]) => (
            <label
              key={id}
              className={`relative mb-2 flex cursor-pointer items-center justify-center gap-4 rounded-2xl border p-4 has-[:focus-visible]:outline has-[:focus-visible]:outline-2 ${provider === id ? "border-primary/40 bg-primary/5" : "border-border"}`}
            >
              <input
                type="radio"
                name="assistant-provider"
                aria-label={name}
                checked={provider === id}
                disabled={pending}
                onChange={() => onProvider(id)}
                className="absolute inset-0 z-10 m-0 h-full w-full cursor-pointer appearance-none rounded-2xl border-0 bg-transparent focus:outline-none"
              />
              <ProviderIcon provider={id} className="h-8 w-8" />
              <span className="w-36 min-w-0">
                <span className="block text-sm font-medium">{name}</span>
                <span className="mt-1 block text-xs text-muted-foreground">
                  {description}
                </span>
              </span>
              {provider === id && (
                <span
                  aria-label="Selected"
                  className="absolute right-4 text-primary"
                >
                  <Check size={14} />
                </span>
              )}
            </label>
          ))}
        </fieldset>
      )}
      {linked && (
        <p className="text-xs text-muted-foreground">
          Linked to an earlier conversation. Its history remains available.
        </p>
      )}
    </div>
  );
}
