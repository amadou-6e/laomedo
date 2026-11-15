import { useRef } from "react";
import ConnectionNavigation from "./ConnectionNavigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export default function ConnectionForms({
  busy,
  submit,
  close,
  inline = false,
  id,
}: {
  busy: boolean;
  submit: (value: Record<string, unknown>) => void;
  close: () => void;
  inline?: boolean;
  id?: string;
}) {
  const formRef = useRef<HTMLFormElement>(null);
  const form = (
    <form
      ref={formRef}
      id={id}
      className={inline ? "gc-token-inline" : "gc-panel gc-focus"}
      onSubmit={(event) => {
        event.preventDefault();
        const form = event.currentTarget;
        const values = Object.fromEntries(new FormData(form).entries());
        form.reset();
        submit(values);
      }}
    >
      {!inline && <h2>Connect with a token</h2>}
      <p className="gc-muted">
        Use a fine-grained personal access token from GitHub. Laomedo will
        verify the account and its repository access.
      </p>
      <label className="gc-field">
        <Input
          aria-label="Personal access token"
          placeholder="Personal access token"
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
    </form>
  );
  return inline ? (
    form
  ) : (
    <div className="gc-screen">
      {form}
      <ConnectionNavigation
        busy={busy}
        back={() => {
          formRef.current?.reset();
          close();
        }}
      />
    </div>
  );
}
