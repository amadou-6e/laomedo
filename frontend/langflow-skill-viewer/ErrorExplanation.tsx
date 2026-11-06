import type { NodeFailure } from "./nodeErrors";

export function formatErrorCopy(failure: NodeFailure): string {
  return [failure.title, failure.description, failure.recovery, JSON.stringify(failure.diagnostics, null, 2)].filter(Boolean).join("\n\n");
}

export default function ErrorExplanation({ failure }: { failure: NodeFailure }) {
  return <div className="select-text"><p>{failure.description}</p>{failure.recovery && <p className="mt-2">{failure.recovery}</p>}
    <details className="mt-2 text-xs"><summary className="cursor-pointer">Technical details</summary><pre style={{ fontFamily: "inherit" }} className="my-2 select-text whitespace-pre-wrap break-all text-xs">{JSON.stringify(failure.diagnostics, null, 2)}</pre></details></div>;
}
