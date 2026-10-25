import ApplicationErrorPopup from "./ApplicationErrorPopup";
import RecoveryPopup from "@/components/laomedoRecovery/RecoveryPopup";
import { isRunnerConnectionError } from "@/components/laomedoRecovery/RunnerRecovery";
import { useState } from "react";
import PopupFrame, { popupButtonStyle } from "@/components/laomedoRecovery/PopupFrame";
import { describeNodeFailure, type ErrorContext, type NodeFailure } from "./nodeErrors";
export default function ErrorPopup({ message, status, context = {}, failure: supplied, onDismiss, autoFocus = true }: {
  message?: unknown; status?: unknown; context?: ErrorContext; failure?: NodeFailure; onDismiss: () => void; autoFocus?: boolean;
}) {
  const failure = supplied ?? describeNodeFailure(message, status, context), [copied, setCopied] = useState("");
  const name = (context.nodeLabel || context.nodeType || "Application").replace(/^Laomedo\s*/, "").slice(0, 120);
  const diagnostics = JSON.stringify(failure.diagnostics, null, 2);
  const copy = async () => {
    try { await navigator.clipboard.writeText([failure.title, failure.description, failure.recovery, diagnostics].filter(Boolean).join("\n\n")); setCopied("Copied"); }
    catch { setCopied("Copy unavailable. Select the error text to copy it manually."); }
  };
  return <PopupFrame label="Error details" code={failure.diagnostics.code} nodeId={failure.diagnostics.node_id} operation={failure.diagnostics.operation} autoFocus={autoFocus} onClose={onDismiss}
    heading={<><h3 className="text-sm font-bold">{failure.title}</h3><span className="w-full min-w-0 break-words text-sm text-muted-foreground">{name}{failure.diagnostics.operation ? ` / ${failure.diagnostics.operation}` : ""}</span></>}
    footer={<><button type="button" style={popupButtonStyle} onClick={() => void copy()}>Copy error</button><button type="button" style={{ ...popupButtonStyle, width: 112, maxWidth: "100%" }} onClick={onDismiss}>Dismiss</button></>}>
    <div className="select-text"><p>{failure.description}</p>{failure.recovery && <p className="mt-2">{failure.recovery}</p>}
    <details className="mt-2 text-xs"><summary className="cursor-pointer">Technical details</summary><pre style={{ fontFamily: "inherit" }} className="my-2 select-text whitespace-pre-wrap break-all text-xs">{diagnostics}</pre></details></div>
    {copied && <p role="status" className="mt-2">{copied}</p>}
  </PopupFrame>;
}

export function FlowErrorPopup({ message, context, onDismiss, laomedo = true }: { message: unknown; context: ErrorContext; onDismiss: () => void; laomedo?: boolean }) {
  if (!laomedo) return <ApplicationErrorPopup title="Flow build failed" list={[message]} onDismiss={onDismiss} autoFocus />;
  return isRunnerConnectionError(message) ? <RecoveryPopup message={message} context={context} onDismiss={onDismiss} />
    : <ErrorPopup message={message} context={context} onDismiss={onDismiss} />;
}
