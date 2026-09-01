import type { Candidate, CostRange, DurationRange, JourneyLeg, JourneyPlan, TravelMode } from "./types";

export const modeLabels: Record<TravelMode, string> = {
  road: "Road", rail: "Rail", air: "Flight", metro: "Metro", bus: "Bus", auto_cab: "Auto/Cab", walking: "Walk",
};

export const modeImages: Record<TravelMode, string> = {
  road: "coastal-cab.png", rail: "coastal-train.png", air: "coastal-plane.png", metro: "coastal-train.png", bus: "coastal-bus.png", auto_cab: "coastal-auto-rickshaw.png", walking: "coastal-traveller-with-luggage.png",
};

export function formatDuration(range?: DurationRange | null, approximate = false) {
  if (!range) return "Unavailable";
  const value = range.minimum_minutes === range.maximum_minutes ? minutes(range.minimum_minutes) : `${minutes(range.minimum_minutes)}–${minutes(range.maximum_minutes)}`;
  return approximate ? `Approx. ${value}` : value;
}

function minutes(value: number) {
  const hours = Math.floor(value / 60); const rest = value % 60;
  if (!hours) return `${rest} min`;
  if (!rest) return `${hours}h`;
  return `${hours}h ${rest}m`;
}

export function formatCostRange(range?: CostRange | null) {
  if (!range) return "Unavailable";
  const number = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });
  return range.minimum === range.maximum ? `₹${number.format(range.minimum)}` : `₹${number.format(range.minimum)}–₹${number.format(range.maximum)}`;
}

export function candidateCost(candidate: Candidate) {
  const range = candidate.cost?.total ?? candidate.cost?.self_drive_total ?? null;
  return formatCostRange(range);
}

export function costBasis(candidate: Candidate) {
  const basis = candidate.cost?.basis ?? candidate.cost?.self_drive_basis;
  return basis === "per_vehicle" ? "per vehicle" : basis === "per_person" ? "per person" : "basis unavailable";
}

export function transferLabel(candidate: Candidate) {
  if (candidate.status === "unavailable") return "Unavailable";
  return candidate.transfer_count === 0 ? "No transfers" : `${candidate.transfer_count} ${candidate.transfer_count === 1 ? "transfer" : "transfers"}`;
}

export function candidateLabel(candidate: Candidate) {
  return candidate.recommended ? `Recommended · ${modeLabels[candidate.mode]}` : modeLabels[candidate.mode];
}

export function candidateTitle(candidate: Candidate) {
  if (candidate.status === "unavailable") return candidate.unavailable_reason || `No ${modeLabels[candidate.mode]} options available`;
  const main = candidate.legs.find((leg) => leg.role === "main") ?? candidate.legs[0];
  if (!main) return `${modeLabels[candidate.mode]} journey`;
  if (main.service_name) return main.service_name;
  if (candidate.mode === "road") return `Drive from ${main.origin.name} to ${main.destination.name}`;
  return `${modeLabels[candidate.mode]} via ${main.destination.name}`;
}

export function dateLabel(value?: string | null, long = false) {
  if (!value) return "Date not supplied";
  const parsed = new Date(`${value}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat("en-GB", long ? { day: "numeric", month: "long", year: "numeric" } : { day: "numeric", month: "short" }).format(parsed);
}

export function candidateSummary(candidate: Candidate) {
  return `${formatDuration(candidate.total_duration)} · ${candidateCost(candidate)} ${costBasis(candidate)} · ${transferLabel(candidate)}`;
}

export function legDetail(leg: JourneyLeg, candidate?: Candidate) {
  const service = [leg.service_name, leg.service_code].filter(Boolean).join(" · ");
  const roadCost = candidate?.mode === "road" && candidate.legs.length === 1 ? candidate.cost?.self_drive_total : null;
  const cost = leg.cost
    ? `${formatCostRange(leg.cost.range)} ${leg.cost.basis === "per_vehicle" ? "per vehicle" : "per person"}`
    : roadCost
      ? `${formatCostRange(roadCost)} self-drive per vehicle`
      : null;
  return [formatDuration(leg.duration, true), service, cost].filter(Boolean).join(" · ");
}

export function routeTitle(plan: JourneyPlan) { return `${plan.origin.name} → ${plan.destination.name}`; }

export function candidateForId(plan: JourneyPlan, id?: string) { return plan.candidates.find((candidate) => candidate.candidate_id === id); }
