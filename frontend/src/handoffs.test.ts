import { describe, expect, it } from "vitest";
import { buildHandoff } from "./handoffs";
import { developmentPlan } from "./api";

describe("external handoffs", () => {
  it("builds a URL-encoded Google Maps driving URL from the selected road journey", () => {
    const road = developmentPlan.candidates.find((item) => item.mode === "road")!;
    const result = buildHandoff(developmentPlan, road);
    expect(result.url).toContain("google.com/maps/dir/?api=1");
    expect(result.url).toContain("travelmode=driving");
    expect(result.url).toContain("origin=Kochi+Airport");
    expect(result.prefillSupported).toBe(true);
  });

  it("is explicit when IRCTC and Ixigo prefill is unsupported", () => {
    for (const mode of ["rail", "air"]) {
      const candidate = developmentPlan.candidates.find((item) => item.mode === mode)!;
      const result = buildHandoff(developmentPlan, candidate);
      expect(result.prefillSupported).toBe(false);
      expect(result.fallback).toContain("does not publish a stable supported prefill URL");
    }
  });
});
