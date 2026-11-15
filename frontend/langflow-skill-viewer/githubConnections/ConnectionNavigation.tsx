import { ArrowLeft, RefreshCw } from "lucide-react";

export default function ConnectionNavigation({
  back,
  refresh,
  busy,
}: {
  back: () => void;
  refresh?: () => void;
  busy: boolean;
}) {
  return (
    <nav className="gc-navigation" aria-label="Connection navigation">
      <button
        type="button"
        className="gc-link gc-icon"
        aria-label="Back to connections"
        title="Back to connections"
        disabled={busy}
        onClick={back}
      >
        <ArrowLeft size={20} aria-hidden="true" />
      </button>
      {refresh && (
        <button
          type="button"
          className="gc-link gc-icon"
          aria-label="Refresh"
          title="Refresh connections"
          disabled={busy}
          onClick={refresh}
        >
          <RefreshCw size={20} aria-hidden="true" />
        </button>
      )}
    </nav>
  );
}
