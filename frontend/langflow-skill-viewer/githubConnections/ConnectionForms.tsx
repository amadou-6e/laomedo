import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export default function ConnectionForms({
  busy,
  submit,
  close,
  inline = false,
}: {
  busy: boolean;
  submit: (value: Record<string, unknown>) => void;
  close: () => void;
  inline?: boolean;
}) {
  return (
    <form
      className={inline ? "gc-token-inline" : "gc-panel gc-focus"}
      onSubmit={(event) => {
        event.preventDefault();
        const form = event.currentTarget;
        const values = Object.fromEntries(new FormData(form).entries());
        form.reset();
        submit(values);
      }}
    >
      {!inline && (
        <button
          type="button"
          className="gc-link gc-back"
          disabled={busy}
          onClick={(event) => {
            event.currentTarget.form?.reset();
            close();
          }}
        >
          ← Back
        </button>
      )}
      {!inline && <h2>Connect with a token</h2>}
      <p className="gc-muted">
        Use a fine-grained personal access token from GitHub. Laomedo will
        verify the account and its repository access.
      </p>
      <label className="gc-field">
        Personal access token
        <Input
          name="token"
          type="password"
          required
          autoComplete="new-password"
          maxLength={4096}
          disabled={busy}
        />
      </label>
      <Button type="submit" disabled={busy}>
        Verify token
      </Button>
      {!inline && (
        <Button
          type="button"
          variant="ghost"
          disabled={busy}
          onClick={(event) => {
            event.currentTarget.form?.reset();
            close();
          }}
        >
          Cancel
        </Button>
      )}
    </form>
  );
}
