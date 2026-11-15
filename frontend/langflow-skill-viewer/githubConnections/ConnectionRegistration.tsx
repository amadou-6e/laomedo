import { ChevronDown, ChevronRight } from "lucide-react";
import ConnectionForms from "./ConnectionForms";
import ConnectionNavigation from "./ConnectionNavigation";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { connectionRequest } from "./api";

/** Prepare the private GitHub App owned by the account being connected. */
export default function ConnectionRegistration({
  close,
  token,
}: {
  close: () => void;
  token?: (payload: Record<string, unknown>) => void;
}) {
  const active = useRef(true);
  useEffect(() => {
    active.current = true;
    return () => {
      active.current = false;
    };
  }, []);
  const [busy, setBusy] = useState(false);
  const [tokenOpen, setTokenOpen] = useState(false);
  const [failed, setFailed] = useState(
    new URLSearchParams(window.location.search).get("registration") ===
      "unconfirmed",
  );
  async function register() {
    setBusy(true);
    setFailed(false);
    try {
      const result = await connectionRequest("provision");
      if (!active.current) return;
      const value = result.outcome as { action?: unknown; manifest?: unknown };
      if (typeof value?.action !== "string" || !value.manifest)
        throw new Error();
      const url = new URL(value.action);
      if (
        url.origin !== "https://github.com" ||
        url.pathname !== "/settings/apps/new" ||
        url.username ||
        url.password ||
        url.hash
      )
        throw new Error();
      const form = document.createElement("form");
      form.method = "post";
      form.action = url.href;
      const manifest = document.createElement("input");
      manifest.type = "hidden";
      manifest.name = "manifest";
      manifest.value = JSON.stringify(value.manifest);
      form.append(manifest);
      document.body.append(form);
      form.submit();
      form.remove();
    } catch {
      if (!active.current) return;
      setFailed(true);
      setBusy(false);
    }
  }
  return (
    <div className="gc-screen">
      <section className="gc-panel gc-focus">
        <h2>Connect your GitHub account</h2>
        <p className="gc-muted">
          Continue to GitHub to connect your account and choose repositories.
          Laomedo fills in the setup for you.
        </p>
        <p className="gc-muted">
          Confirm that GitHub shows the account you want to connect before
          approving. The connection stays private to that account.
        </p>
        {failed && (
          <p role="alert">
            Setup could not be confirmed. Check your GitHub Apps before starting
            again; an App may already have been created.
          </p>
        )}
        <Button ignoreTitleCase disabled={busy} onClick={() => void register()}>
          {busy ? "Opening GitHub…" : "Continue on GitHub"}
        </Button>
        {token && (
          <div className="gc-advanced">
            <button
              type="button"
              className="gc-link"
              disabled={busy}
              aria-expanded={tokenOpen}
              aria-controls="gc-registration-token"
              onClick={() => setTokenOpen(!tokenOpen)}
            >
              {tokenOpen ? (
                <ChevronDown size={16} aria-hidden="true" />
              ) : (
                <ChevronRight size={16} aria-hidden="true" />
              )}{" "}
              Use a personal access token instead
            </button>
            {tokenOpen && (
              <ConnectionForms
                inline
                id="gc-registration-token"
                busy={busy}
                close={() => setTokenOpen(false)}
                submit={token}
              />
            )}
          </div>
        )}
      </section>
      <ConnectionNavigation busy={busy} back={close} />
    </div>
  );
}
