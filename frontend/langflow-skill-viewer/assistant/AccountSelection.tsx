import { useId, useState } from "react";
import { Check, ChevronDown, ChevronRight } from "lucide-react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import ProviderIcon from "./ProviderIcon";
import type { SavedConnection } from "./models";

export default function AccountSelection({ accounts, provider, selected, generation, disabled, loading = false, onSelect }: {
  provider: string;
  accounts: SavedConnection[]; selected?: string | null; generation?: number | null;
  disabled: boolean; onSelect: (account: SavedConnection) => void;
  loading?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const labelId = useId();
  const current = accounts.find(item => item.connection_id === selected && item.generation === generation);
  const providerName = ({ codex: "Codex", claude: "Claude", opencode: "OpenCode" } as Record<string, string>)[provider] ?? provider;
  const connected = accounts.filter(item => item.lifecycle === "connected");
  return <div className="relative mr-auto min-w-0 text-xs">
    <Popover open={open && !disabled} onOpenChange={setOpen}>
    <PopoverTrigger asChild>
    <button type="button" aria-label="Account" aria-describedby={labelId} aria-expanded={open && !disabled} disabled={disabled}
      title={current?.label ?? `${providerName} account`}
      className="flex max-w-52 items-center gap-1.5 rounded-md border border-border/50 bg-foreground/5 px-2 py-1 text-muted-foreground hover:bg-foreground/10 focus-visible:outline focus-visible:outline-2 disabled:opacity-70">
      <ProviderIcon provider={provider} className="h-3.5 w-3.5" />
      <span id={labelId} className="truncate">{current?.label ?? (selected ? "Account unavailable" : loading ? "Loading accounts…" : connected.length ? "Select an account" : "No account available")}</span>
      {!disabled && <ChevronDown size={12} />}
    </button>
    </PopoverTrigger>
    <PopoverContent align="start" side="top" sideOffset={8} role="menu" aria-label="Saved accounts"
      className="w-64 max-w-[calc(100vw-2rem)] rounded-lg border-border/60 bg-muted p-1 text-xs shadow-lg"
      onKeyDown={event => {
        if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
        event.preventDefault();
        const items = Array.from(event.currentTarget.querySelectorAll<HTMLElement>('[role="menuitemradio"], [role="menuitem"]'));
        const currentIndex = items.indexOf(document.activeElement as HTMLElement);
        items[(currentIndex + (event.key === "ArrowDown" ? 1 : items.length - 1)) % items.length]?.focus();
      }}>
      <p className="px-2 py-1.5 text-[10px] text-muted-foreground">{providerName} accounts</p>
      {connected.map(item => <button key={item.connection_id} type="button" role="menuitemradio" aria-checked={item.connection_id === selected && item.generation === generation}
        className={`flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-xs text-foreground/85 hover:bg-foreground/10 focus:bg-foreground/10 focus:outline-none ${item.connection_id === selected && item.generation === generation ? "bg-foreground/10" : ""}`}
        onClick={() => { onSelect(item); setOpen(false); }}><ProviderIcon provider={provider} className="h-3.5 w-3.5" /><span className="min-w-0 flex-1 truncate">{item.label}</span>{item.connection_id === selected && item.generation === generation && <Check size={12} aria-hidden="true" />}</button>)}
      {!connected.length && <p className="px-2 py-2 text-muted-foreground">{loading ? "Loading accounts…" : `No connected ${providerName} account.`}</p>}
      <div className="mt-1 border-t border-border/60 pt-1">
        <a role="menuitem" href="/settings/providers" className="flex items-center justify-between rounded px-2 py-1.5 text-muted-foreground hover:bg-foreground/10 focus:bg-foreground/10 focus:outline-none">Manage accounts<ChevronRight size={12} aria-hidden="true" /></a>
      </div>
    </PopoverContent>
    </Popover>
  </div>;
}
