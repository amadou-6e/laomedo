import CopyIcon from "@/components/laomedoErrors/CopyIcon";
import { useRef } from "react";
import PopupFrame, { popupButtonStyle } from "./PopupFrame";
import RunnerRecovery, { DOCKER_INSTALL_URL, PREREQUISITE_CODES } from "./RunnerRecovery";
import { describeNodeFailure, type ErrorContext } from "@/components/laomedoErrors/nodeErrors";

export default function RecoveryPopup({ message, context, onDismiss }: {
  message: unknown; context: ErrorContext; onDismiss: () => void;
}) {
  const dismissRef = useRef(onDismiss);
  dismissRef.current = onDismiss;
  const failure = describeNodeFailure(message, undefined, context);
  const name = (context.nodeLabel || context.nodeType || "Agent").replace(/^Laomedo\s*/, "").slice(0, 120);
  const buttonStyle = popupButtonStyle;
  return <RunnerRecovery message={message}>{recovery => {
    const checking = !recovery.state && !recovery.error;
    const busy = checking || recovery.waiting || recovery.cancelling;
    const close = async () => { if (!busy || await recovery.cancel()) dismissRef.current(); };
    const diagnostics = JSON.stringify({ ...failure.diagnostics,
      ...(PREREQUISITE_CODES.includes(recovery.reason ?? "") ? { recovery_code: recovery.reason } : {}) }, null, 2);
    return <PopupFrame label="Local backend recovery" code={failure.diagnostics.code} nodeId={failure.diagnostics.node_id} operation={failure.diagnostics.operation} onClose={() => void close()}
      tools={!busy && <CopyIcon label="Copy diagnostics" text={diagnostics} />}
      heading={<><h3 className="text-sm font-bold">{recovery.title || failure.title}</h3><span className="min-w-0 break-words text-sm text-muted-foreground">{"\u00b7"} {name}{failure.diagnostics.operation ? ` / ${failure.diagnostics.operation}` : ""}</span></>}
      footer={<>
        {(recovery.canStart || recovery.waiting) && <button type="button" onClick={recovery.restart} disabled={recovery.waiting} style={{ ...buttonStyle, width: 196, maxWidth: "100%" }}
          className="disabled:opacity-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2">
          {recovery.waiting ? "Starting..." : "Start local runner"}
        </button>}
        {recovery.installDocker && <a href={DOCKER_INSTALL_URL} target="_blank" rel="noopener noreferrer" aria-label="Install Docker (opens in a new tab)" style={{ ...buttonStyle, width: 196, maxWidth: "100%" }}
          className="flex items-center justify-center gap-2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2">Install Docker <span aria-hidden="true">{"\u2197"}</span></a>}
        <button type="button" onClick={() => void close()} disabled={recovery.cancelling} style={{ ...buttonStyle, width: 112, maxWidth: "100%" }} className="focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2">{recovery.cancelling ? "Cancelling..." : busy ? "Cancel" : "Dismiss"}</button>

      </>}>
        <p role="status" aria-busy={busy} className="flex items-center gap-2">{busy && <svg aria-hidden="true" className="h-4 w-4 shrink-0 animate-spin motion-reduce:animate-none" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2" opacity="0.25" /><path d="M12 3a9 9 0 0 1 9 9" stroke="currentColor" strokeWidth="2" strokeLinecap="round" /></svg>}<span>{recovery.cancelling ? "Cancelling runner startup..." : recovery.message}</span></p>
        {!busy && recovery.guidance && <p className="mt-2">{recovery.guidance}</p>}
        {!busy && failure.diagnostics.code !== "runner_model_catalog_unavailable_check_runner_connection" && PREREQUISITE_CODES.includes(recovery.reason ?? "") && <p className="mt-2">The previous run's outcome is unconfirmed.</p>}
        {!busy && recovery.error && <p role="alert" className="mt-2">{recovery.error}</p>}
        {!busy && <details className="mt-2 text-xs"><summary className="cursor-pointer">Technical details</summary>
          <pre style={{ fontFamily: "inherit" }} className="my-2 select-text whitespace-pre-wrap break-all text-xs">{diagnostics}</pre>
        </details>}
    </PopupFrame>
  }}</RunnerRecovery>;
}
