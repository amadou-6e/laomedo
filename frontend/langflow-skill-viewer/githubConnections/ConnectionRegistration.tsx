import { ChevronDown, ChevronRight, ExternalLink, Github } from "lucide-react";
import ConnectionForms from "./ConnectionForms";
import ConnectionNavigation from "./ConnectionNavigation";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { connectionRequest } from "./api";

/** Prepare the private GitHub App owned by the account being connected. */
export default function ConnectionRegistration({
  close,
  token,
  busy: parentBusy = false,
}: {
  busy?: boolean;
  close: () => void;
  token?: (payload: Record<string, unknown>) => void;
}) {
  const active = useRef(true);
  const inFlight = useRef(false);
  useEffect(() => {
    active.current = true;
    const restore = (event: PageTransitionEvent) => {
      if (event.persisted) {
        inFlight.current = false;
        setBusy(false);
      }
    };
    window.addEventListener("pageshow", restore);
    return () => {
      window.removeEventListener("pageshow", restore);
      active.current = false;
    };
  }, []);
  const [registering, setBusy] = useState(false);
  const busy = registering || parentBusy;
  const [tokenOpen, setTokenOpen] = useState(false);
  const [failed, setFailed] = useState(
    new URLSearchParams(window.location.search).get("registration") ===
      "unconfirmed",
  );
  async function register() {
    if (busy || inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setFailed(false);
    try {
      const result = await connectionRequest("provision");
      if (!active.current) return;
      const value = result.outcome as { action?: unknown; manifest?: unknown };
      if (
        typeof value?.action !== "string" ||
        typeof value.manifest !== "object" ||
        value.manifest === null ||
        !("public" in value.manifest) ||
        value.manifest.public !== false
      )
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
      inFlight.current = false;
      setFailed(true);
      setBusy(false);
    }
  }
  return (
    <div className="gc-screen">
      <section className="gc-panel gc-focus gc-registration">
        <div className="gc-setup-heading">
          <span className="gc-avatar" aria-hidden="true">
            <Github size={24} />
          </span>
          <div>
            <p className="gc-eyebrow">One-time setup</p>
            <h2>Connect a GitHub account</h2>
          </div>
        </div>
        <p className="gc-muted">
          A private connection for this account. No credentials to copy.
        </p>
        <ol className="gc-setup-steps">
          <li>
            <h3>Choose your account</h3>
            <p className="gc-muted">
              Open GitHub and select the account you want to connect from its
              profile menu. Then return here.
            </p>
            <Button asChild ignoreTitleCase variant="outline">
              <a
                href="https://github.com/"
                target="_blank"
                rel="noopener noreferrer"
              >
                Open GitHub <ExternalLink size={16} aria-hidden="true" />
              </a>
            </Button>
          </li>
          <li>
            <h3>Approve the connection</h3>
            <p className="gc-muted">
              Continue to the prefilled setup on GitHub. Check the account shown
              as the owner before approving.
            </p>
          </li>
        </ol>
        <p className="gc-muted gc-setup-note">
          Already connected this account? Go back and open its existing
          connection instead.
        </p>
        {failed && (
          <p role="alert">
            Setup could not be confirmed. Check your GitHub Apps before starting
            again; an App may already have been created. Delete it on GitHub if
            it was created for the wrong account.
          </p>
        )}
        <Button ignoreTitleCase disabled={busy} onClick={() => void register()}>
          {registering ? "Opening GitHub…" : "Continue to GitHub"}
        </Button>
        <p className="gc-muted gc-setup-note">
          Next, choose the repositories Laomedo can read.
        </p>
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
