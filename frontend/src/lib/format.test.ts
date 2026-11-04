import { describe, expect, it } from "vitest";
import { formatActualTotal, formatMs, formatPercent, formatUsd } from "./format";

describe("formatting", () => {
  it("never presents an unknown charge as $0", () => {
    expect(formatActualTotal({ actual_charge_usd: "0E-8", actual_charge_known_requests: 0 })).toBe("unknown");
    expect(formatActualTotal({ actual_charge_usd: "0E-8", actual_charge_known_requests: 3 })).toBe("$0");
  });

  it("formats tiny shadow costs readably", () => {
    expect(formatUsd("0.00022500")).toBe("$0.000225");
    expect(formatUsd("12.5")).toBe("$12.50");
    expect(formatUsd(null)).toBe("—");
    expect(formatUsd("not-a-number")).toBe("—");
  });

  it("formats latency and percentages", () => {
    expect(formatMs(850)).toBe("850 ms");
    expect(formatMs(1900)).toBe("1.90 s");
    expect(formatPercent(0.6667)).toBe("66.7%");
    expect(formatPercent(null)).toBe("—");
  });
});
