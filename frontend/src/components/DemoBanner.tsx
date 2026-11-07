/**
 * Shown whenever the gateway can only produce simulated responses. Never hidden by CSS. It speaks
 * about interactive requests only: the same database also holds benchmark records written from the
 * CLI, which may include real provider calls.
 */
export function DemoBanner() {
  return (
    <div
      role="note"
      className="border-b border-warn/40 bg-warn/10 px-4 py-2 text-center text-sm text-ink"
    >
      <strong className="font-semibold">DEMO — simulated responses.</strong> Interactive production
      requests use simulated responses through the mock provider. Historical evaluation records may
      include real provider calls; those records are not live production traffic.
    </div>
  );
}
