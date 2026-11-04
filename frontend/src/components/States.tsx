import type { ApiError } from "../api/client";

export function LoadingState({ label = "Loading…" }: { label?: string }) {
  return (
    <div role="status" aria-live="polite" className="flex items-center gap-3 p-6 text-sm text-muted">
      <span className="size-4 animate-spin rounded-full border-2 border-line border-t-accent" />
      {label}
    </div>
  );
}

export function EmptyState({ title, children }: { title: string; children?: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-dashed border-line p-8 text-center">
      <p className="font-medium text-ink">{title}</p>
      {children ? <div className="mt-2 text-sm text-muted">{children}</div> : null}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: ApiError; onRetry?: () => void }) {
  return (
    <div role="alert" className="rounded-lg border border-danger/40 bg-danger/5 p-4 text-sm">
      <p className="font-medium text-danger">{error.message}</p>
      <p className="mt-1 text-muted">
        Code <code className="font-mono">{error.code}</code>
        {error.requestId ? (
          <>
            {" "}
            · request <code className="font-mono">{error.requestId}</code>
          </>
        ) : null}
      </p>
      {onRetry ? (
        <button
          type="button"
          onClick={onRetry}
          className="mt-3 rounded-md border border-line bg-surface px-3 py-1.5 font-medium hover:bg-sunken"
        >
          Retry
        </button>
      ) : null}
    </div>
  );
}
