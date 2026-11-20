import { useState } from "react";
import { Check, ChevronDown } from "lucide-react";
import type { SavedConnection } from "./models";

export default function AccountSelection({ accounts, selected, generation, disabled, onSelect }: {
  accounts: SavedConnection[]; selected?: string | null; generation?: number | null;
  disabled: boolean; onSelect: (account: SavedConnection) => void;
}) {
  const [open, setOpen] = useState(false);
  const current = accounts.find(item => item.connection_id === selected && item.generation === generation);
  return <div className="relative mr-auto min-w-0 text-xs">
    <button type="button" aria-label="Account" aria-expanded={open} disabled={disabled}
      className="flex max-w-52 items-center gap-1 rounded px-2 py-1 text-muted-foreground hover:bg-muted disabled:opacity-70"
      onClick={() => setOpen(value => !value)}>
      <span className="truncate">{current?.label ?? (selected ? "Account unavailable" : "Select account")}</span>
      {!disabled && <ChevronDown size={12} />}
    </button>
    {open && !disabled && <div role="menu" aria-label="Saved accounts" className="absolute bottom-full left-0 z-30 mb-2 w-64 rounded-xl border bg-popover p-1 shadow-lg">
      {accounts.filter(item => item.lifecycle === "connected").map(item => <button key={item.connection_id} type="button" role="menuitemradio" aria-checked={item.connection_id === selected && item.generation === generation}
        className="flex w-full items-center justify-between gap-2 rounded-lg px-3 py-2 text-left text-sm hover:bg-muted"
        onClick={() => { onSelect(item); setOpen(false); }}><span className="truncate">{item.label}</span>{item.connection_id === selected && item.generation === generation && <Check size={12} />}</button>)}
      {!accounts.some(item => item.lifecycle === "connected") && <p className="px-3 py-2 text-muted-foreground">Connect an account in Settings to start chatting.</p>}
    </div>}
  </div>;
}
