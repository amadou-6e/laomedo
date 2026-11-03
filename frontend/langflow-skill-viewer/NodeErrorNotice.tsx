import { useState } from "react";
import RecoveryPopup from "@/components/laomedoRecovery/RecoveryPopup";
import { isRunnerConnectionError } from "@/components/laomedoRecovery/RunnerRecovery";
import ErrorPopup from "./ErrorPopup";
import { describeNodeFailure, type ErrorContext } from "./nodeErrors";
export default function NodeErrorNotice({ message, status, context, inline = false }: {
  message?: unknown; status?: unknown; context: ErrorContext; inline?: boolean;
}) {
  const [open, setOpen] = useState(inline), failure = describeNodeFailure(message, status, context);
  const show = () => {
    const existing = [...document.querySelectorAll<HTMLElement>("[data-error-code]")].find(card => card.dataset.errorCode === failure.diagnostics.code && card.dataset.errorNode === failure.diagnostics.node_id && card.dataset.errorOperation === failure.diagnostics.operation);
    if (existing) existing.focus({ preventScroll: true }); else setOpen(true);
  };
  return <>{!inline && <button type="button" onClick={show} className="nodrag nopan rounded px-1 py-0.5 text-xs font-medium text-error-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    aria-label={`Error details: ${failure.title}`} title={failure.title}>Error details</button>}
    {open && (isRunnerConnectionError(message) ? <RecoveryPopup message={message} context={context} onDismiss={() => setOpen(false)} />
      : <ErrorPopup message={message} status={status} context={context} onDismiss={() => setOpen(false)} />)}</>;
}
