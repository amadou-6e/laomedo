import CopyIcon from "./CopyIcon";
import ErrorExplanation, { formatErrorCopy } from "./ErrorExplanation";
import ApplicationErrorPopup from "./ApplicationErrorPopup";
import RecoveryPopup from "@/components/laomedoRecovery/RecoveryPopup";
import { isRunnerConnectionError } from "@/components/laomedoRecovery/RunnerRecovery";
import PopupFrame, { popupButtonStyle } from "@/components/laomedoRecovery/PopupFrame";
import { describeNodeFailure, type ErrorContext, type NodeFailure } from "./nodeErrors";
export default function ErrorPopup({ message, status, context = {}, failure: supplied, onDismiss, autoFocus = true }: {
  message?: unknown; status?: unknown; context?: ErrorContext; failure?: NodeFailure; onDismiss: () => void; autoFocus?: boolean;
}) {
  const failure = supplied ?? describeNodeFailure(message, status, context);
  const name = (context.nodeLabel || context.nodeType || "Application").replace(/^Laomedo\s*/, "").slice(0, 120);
  return <PopupFrame label="Error details" code={failure.diagnostics.code} nodeId={failure.diagnostics.node_id} operation={failure.diagnostics.operation} autoFocus={autoFocus} onClose={onDismiss}
    tools={<CopyIcon text={formatErrorCopy(failure)} />}
    heading={<><h3 className="text-sm font-bold">{failure.title}</h3><span className="w-full min-w-0 break-words text-sm text-muted-foreground">{name}{failure.diagnostics.operation ? ` / ${failure.diagnostics.operation}` : ""}</span></>}
    footer={<><button type="button" style={{ ...popupButtonStyle, width: 112, maxWidth: "100%" }} onClick={onDismiss}>Dismiss</button></>}>
    <ErrorExplanation failure={failure} />
  </PopupFrame>;
}

export function FlowErrorPopup({ message, context, onDismiss, laomedo = true }: { message: unknown; context: ErrorContext; onDismiss: () => void; laomedo?: boolean }) {
  if (!laomedo) return <ApplicationErrorPopup title="Flow build failed" list={[message]} onDismiss={onDismiss} autoFocus />;
  return isRunnerConnectionError(message) ? <RecoveryPopup message={message} context={context} onDismiss={onDismiss} />
    : <ErrorPopup message={message} context={context} onDismiss={onDismiss} />;
}
