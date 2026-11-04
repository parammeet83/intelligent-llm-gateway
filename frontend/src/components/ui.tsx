import { useEffect, useRef, type ReactNode } from "react";
import { COST_STATUS_LABEL, formatUsd } from "../lib/format";

export function PageHeader({ title, description, actions }: { title: string; description?: string; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <h1 className="text-xl font-semibold">{title}</h1>
        {description ? <p className="mt-1 max-w-3xl text-sm text-muted">{description}</p> : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  );
}

export function Card({ title, children, className = "" }: { title?: string; children: ReactNode; className?: string }) {
  return (
    <section className={`rounded-lg border border-line bg-surface p-4 sm:p-5 ${className}`}>
      {title ? <h2 className="mb-3 text-sm font-medium text-muted">{title}</h2> : null}
      {children}
    </section>
  );
}

export function Kpi({ label, value, hint }: { label: string; value: ReactNode; hint?: ReactNode }) {
  return (
    <div className="rounded-lg border border-line bg-surface p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-muted">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums">{value}</p>
      {hint ? <p className="mt-1 text-xs text-muted">{hint}</p> : null}
    </div>
  );
}

const BADGE_TONES = {
  neutral: "bg-sunken text-muted",
  ok: "bg-ok/10 text-ok",
  warn: "bg-warn/15 text-warn",
  danger: "bg-danger/10 text-danger",
  accent: "bg-accent/10 text-accent",
} as const;

export function Badge({ children, tone = "neutral", title }: { children: ReactNode; tone?: keyof typeof BADGE_TONES; title?: string }) {
  return (
    <span title={title} className={`inline-flex items-center rounded px-1.5 py-0.5 text-xs font-medium ${BADGE_TONES[tone]}`}>
      {children}
    </span>
  );
}

export function StatusBadge({ status }: { status: string }) {
  const tone = status === "succeeded" ? "ok" : status === "pending" ? "warn" : status.startsWith("rejected") ? "warn" : status === "failed" ? "danger" : "neutral";
  return <Badge tone={tone}>{status.replace("_", " ")}</Badge>;
}

export function SimulatedBadge() {
  return (
    <Badge tone="warn" title="Produced by the mock provider: not a real model response">
      simulated
    </Badge>
  );
}

/** A cost with its provenance, so estimates are never read as spending. */
export function CostCell({ amount, status, kind }: { amount: string | null; status: string; kind: "actual" | "list" }) {
  if (kind === "list") {
    return status === "estimated" ? (
      <span title="Estimated at published list price; not money spent">
        {formatUsd(amount)} <span className="text-xs text-muted">est.</span>
      </span>
    ) : (
      <span className="text-muted" title="No verified list price">unknown</span>
    );
  }
  return (
    <span title={COST_STATUS_LABEL[status] ?? status}>
      {status === "unavailable" ? <span className="text-muted">unknown</span> : formatUsd(amount)}{" "}
      {status === "free_tier" ? <span className="text-xs text-muted">free tier</span> : null}
      {status === "reported" ? <span className="text-xs text-muted">reported</span> : null}
    </span>
  );
}

export function Select({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <label className="flex items-center gap-2 text-sm">
      <span className="text-muted">{label}</span>
      <select
        aria-label={label}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-md border border-line bg-surface px-2 py-1.5 text-sm"
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
}

export function Button({
  children,
  onClick,
  variant = "secondary",
  type = "button",
  disabled,
}: {
  children: ReactNode;
  onClick?: () => void;
  variant?: "primary" | "secondary" | "danger";
  type?: "button" | "submit";
  disabled?: boolean;
}) {
  const styles = {
    primary: "bg-accent text-white hover:opacity-90",
    secondary: "border border-line bg-surface hover:bg-sunken",
    danger: "border border-danger/40 text-danger hover:bg-danger/5",
  }[variant];
  return (
    <button type={type} onClick={onClick} disabled={disabled} className={`rounded-md px-3 py-1.5 text-sm font-medium disabled:opacity-50 ${styles}`}>
      {children}
    </button>
  );
}

export function Pagination({ total, limit, offset, onChange }: { total: number; limit: number; offset: number; onChange: (offset: number) => void }) {
  if (total <= limit) return <p className="mt-3 text-xs text-muted">{total} result(s)</p>;
  const page = Math.floor(offset / limit) + 1;
  const pages = Math.ceil(total / limit);
  return (
    <nav aria-label="Pagination" className="mt-3 flex items-center justify-between text-sm">
      <span className="text-muted">
        {offset + 1}–{Math.min(offset + limit, total)} of {total}
      </span>
      <div className="flex gap-2">
        <Button onClick={() => onChange(Math.max(0, offset - limit))} disabled={page <= 1}>
          Previous
        </Button>
        <Button onClick={() => onChange(offset + limit)} disabled={page >= pages}>
          Next
        </Button>
      </div>
    </nav>
  );
}

/** Horizontally scrollable table wrapper, so wide tables never break the mobile layout. */
export function TableWrap({ children }: { children: ReactNode }) {
  return <div className="-mx-4 overflow-x-auto px-4 sm:mx-0 sm:px-0">{children}</div>;
}

export const th = "whitespace-nowrap border-b border-line px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-muted";
export const td = "whitespace-nowrap border-b border-line px-3 py-2 text-sm";

export function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    ref.current?.focus();
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 sm:items-center" onClick={onClose}>
      <div
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        onClick={(e) => e.stopPropagation()}
        className="max-h-[90dvh] w-full overflow-y-auto rounded-t-xl bg-surface p-5 shadow-xl outline-none sm:max-w-3xl sm:rounded-xl"
      >
        <div className="mb-4 flex items-start justify-between gap-4">
          <h2 className="text-lg font-semibold">{title}</h2>
          <Button onClick={onClose}>Close</Button>
        </div>
        {children}
      </div>
    </div>
  );
}
