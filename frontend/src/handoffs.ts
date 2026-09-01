import type { Candidate, JourneyPlan } from "./types";

export type Handoff = { label: string; url: string; prefillSupported: boolean; fallback: string };

export function buildHandoff(plan: JourneyPlan, candidate: Candidate): Handoff {
  const first = candidate.legs[0]?.origin.name ?? plan.origin.name;
  const last = candidate.legs.at(-1)?.destination.name ?? plan.destination.name;
  if (candidate.mode === "road") {
    const params = new URLSearchParams({ api: "1", origin: first, destination: last, travelmode: "driving" });
    const waypoints = candidate.legs.slice(0, -1).map((leg) => leg.destination.name).filter((name) => name !== last).slice(0, 3);
    if (waypoints.length) params.set("waypoints", waypoints.join("|"));
    return { label: "Check live traffic", url: `https://www.google.com/maps/dir/?${params}`, prefillSupported: true, fallback: "Google Maps will show driving directions for this route." };
  }
  const route = `${first} → ${last}${plan.travel_date ? ` on ${plan.travel_date}` : ""}`;
  if (candidate.mode === "rail") return { label: "Check train status", url: "https://www.irctc.co.in/nget/train-search", prefillSupported: false, fallback: `IRCTC does not publish a stable supported prefill URL. Search ${route}.` };
  return { label: "Check flight status", url: "https://www.ixigo.com/flights", prefillSupported: false, fallback: `Ixigo does not publish a stable supported prefill URL. Search ${route}.` };
}
