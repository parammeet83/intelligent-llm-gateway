import { useState, type FormEvent, type ReactNode } from "react";
import { ApiError, api } from "../api/client";
import { useSession } from "../hooks/useSession";
import { Button } from "./ui";

export function LoginPage() {
  const [token, setToken] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.login(token);
      setToken("");
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Sign-in failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="mx-auto mt-10 max-w-md rounded-lg border border-line bg-surface p-6">
      <h1 className="text-lg font-semibold">Administrator sign-in</h1>
      <p className="mt-1 text-sm text-muted">
        Enter the server's admin token. It's exchanged for a short-lived session token; the admin token itself is not stored in the
        browser.
      </p>
      <form onSubmit={submit} className="mt-5 space-y-3">
        <label className="block text-sm">
          <span className="text-muted">Admin token</span>
          <input
            type="password"
            autoComplete="off"
            value={token}
            onChange={(e) => setToken(e.target.value)}
            className="mt-1 w-full rounded-md border border-line bg-canvas px-3 py-2 font-mono"
            required
          />
        </label>
        {error ? (
          <p role="alert" className="text-sm text-danger">
            {error}
          </p>
        ) : null}
        <Button type="submit" variant="primary" disabled={busy || !token}>
          {busy ? "Signing in…" : "Sign in"}
        </Button>
      </form>
    </section>
  );
}

/** Admin-only pages render the sign-in form until a session exists. */
export function RequireAdmin({ children }: { children: ReactNode }) {
  return useSession() ? <>{children}</> : <LoginPage />;
}
