/** Formatting helpers. Money arrives as decimal strings; never coerce "unknown" to 0. */

export function formatUsd(value: string | null | undefined): string {
  if (value === null || value === undefined) return "—";
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  if (n === 0) return "$0";
  if (Math.abs(n) >= 0.01) return `$${n.toFixed(2)}`;
  return `$${n.toPrecision(3)}`; // tiny shadow costs, e.g. $0.000225
}

export function formatPercent(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined) return "—";
  return `${(value * 100).toFixed(digits)}%`;
}

export function formatMs(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return value >= 1000 ? `${(value / 1000).toFixed(2)} s` : `${value} ms`;
}

export function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return new Intl.NumberFormat("en-US").format(value);
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value.endsWith("Z") || value.includes("+") ? value : `${value}Z`);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

/**
 * Total actual charges, or "unknown" when no request in the group had a known charge.
 * A sum over zero known values is not $0, it's unknown.
 */
export function formatActualTotal(stats: { actual_charge_usd: string; actual_charge_known_requests: number }): string {
  return stats.actual_charge_known_requests > 0 ? formatUsd(stats.actual_charge_usd) : "unknown";
}

export const COST_STATUS_LABEL: Record<string, string> = {
  reported: "Reported by provider",
  free_tier: "Free tier ($0)",
  estimated: "Estimated",
  unavailable: "Unknown",
};
