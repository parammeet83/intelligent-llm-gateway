import "@testing-library/jest-dom/vitest";
import { cleanup, configure } from "@testing-library/react";
import { afterEach, vi } from "vitest";

// Pages are lazy-loaded. On a cold first run, compiling a page's chunk can take longer than Testing
// Library's default 1 s wait, which made findBy*/waitFor fail intermittently. Waiting longer changes
// no assertion; a genuinely missing element still fails (after 5 s).
configure({ asyncUtilTimeout: 5000 });

// jsdom has no ResizeObserver; Recharts' ResponsiveContainer needs one.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??= ResizeObserverStub as unknown as typeof ResizeObserver;

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  sessionStorage.clear();
});
