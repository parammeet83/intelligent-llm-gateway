/** Shown whenever the gateway can only produce simulated responses. Never hidden by CSS. */
export function DemoBanner() {
  return (
    <div
      role="note"
      className="border-b border-warn/40 bg-warn/10 px-4 py-2 text-center text-sm text-ink"
    >
      <strong className="font-semibold">DEMO — simulated responses.</strong> Only the mock provider
      is enabled. No real model was called and no figures here describe real usage.
    </div>
  );
}
