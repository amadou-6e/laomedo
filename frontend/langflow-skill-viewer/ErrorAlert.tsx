import ApplicationErrorPopup from "@/components/laomedoErrors/ApplicationErrorPopup";
import ErrorPopup from "@/components/laomedoErrors/ErrorPopup";
import RecoveryPopup from "@/components/laomedoRecovery/RecoveryPopup";
import { isRunnerConnectionError } from "@/components/laomedoRecovery/RunnerRecovery";
import { type NodeFailure } from "@/components/laomedoErrors/nodeErrors";
import type { ErrorAlertType } from "../../types/alerts";

// Persist until dismissed; selecting/copying text never closes an error.
export default function ErrorAlert({ title, list = [], id, removeAlert, failure }: ErrorAlertType & { failure?: NodeFailure }) {
  if (failure && isRunnerConnectionError(failure.diagnostics.code)) return <RecoveryPopup message={failure.diagnostics.code} context={{}} onDismiss={() => removeAlert(id)} />;
  return failure ? <ErrorPopup failure={failure} autoFocus={false} onDismiss={() => removeAlert(id)} />
    : <ApplicationErrorPopup title={title} list={list} onDismiss={() => removeAlert(id)} />;
}
