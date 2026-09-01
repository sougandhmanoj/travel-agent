import type { Candidate, JourneyLeg, JourneyPlan, Mode, TravelMode } from "./types";

const point = (name: string, latitude: number, longitude: number) => ({ name, location: { latitude, longitude } });
const leg = (id: string, mode: TravelMode, from: string, to: string, min: number, max: number, instructions: string, cost?: [number, number]): JourneyLeg => ({
  leg_id: id, role: id === "1" ? "first_mile" : "main", mode,
  origin: point(from, 10.15, 76.39), destination: point(to, 9.93, 78.12),
  duration: { minimum_minutes: min, maximum_minutes: max }, instructions,
  intermediate_stops: [], cost: cost ? { range: { minimum: cost[0], maximum: cost[1], currency: "INR" }, basis: mode === "road" || mode === "auto_cab" ? "per_vehicle" : "per_person", description: "Deterministic development estimate" } : null,
});

const candidate = (id: string, mode: Mode, recommended: boolean, minutes: [number, number], transfers: number, legs: JourneyLeg[], total: [number, number], explanation: string): Candidate => ({
  candidate_id: id, mode, dominant_mode: mode, status: "available", recommended,
  display_slot: recommended ? "recommended" : `${mode}_alternative`, position_explanation: explanation,
  total_duration: { minimum_minutes: minutes[0], maximum_minutes: minutes[1] },
  cost: { total: { minimum: total[0], maximum: total[1], currency: "INR" }, basis: mode === "road" ? "per_vehicle" : "per_person", coverage: "partial_estimate", explanation: "Some local costs may be unavailable." },
  legs, transfer_count: transfers, mode_change_count: Math.max(0, legs.length - 1), station_change_count: 0,
  difficulty: transfers > 1 ? "manageable" : "easy", confidence: "medium",
  warnings: [{ code: "fixture", severity: "info", message: "Development preview only. Verify services, times and fares before travel." }],
  assumptions: ["The selected date is planning context and does not confirm operation."],
  sources: [{ label: "Waystory deterministic fixture", detail: "Local development data", freshness: "unknown" }],
  verification_requirements: [{ subject: mode, required: true, guidance: `Verify the ${mode === "air" ? "flight" : mode} before travelling.` }],
});

export const demoPlan: JourneyPlan = {
  origin: { ...point("Kochi Airport", 10.1518, 76.393), place_id: "hub_00005", code: "COK" },
  destination: { ...point("Madurai", 9.9252, 78.1198), place_id: "tamil_nadu_madurai" },
  travel_date: new Date(Date.now() + 86400000 * 14).toISOString().slice(0, 10), recommended_mode: "rail",
  recommendation_explanation: "Recommended because it is a clearly explained complete journey with supported local connections.",
  developmentPreview: true,
  candidates: [
    candidate("demo-recommended", "rail", true, [665, 705], 1, [leg("1", "auto_cab", "Kochi Airport", "Ernakulam Junction", 45, 65, "Take a cab to Ernakulam Junction", [700, 1000]), leg("2", "rail", "Ernakulam Junction", "Madurai Junction", 580, 600, "Board the listed train and remain onboard at intermediate stops", [650, 1100]), leg("3", "auto_cab", "Madurai Junction", "Madurai", 20, 30, "Take an auto-rickshaw to your destination", [250, 350])], [1600, 2450], "Recommended from the available development patterns."),
    candidate("demo-road", "road", false, [465, 540], 0, [leg("1", "road", "Kochi Airport", "Madurai", 465, 540, "Drive via the provider-returned road route", [2800, 3900])], [2800, 3900], "Road-led complete journey."),
    candidate("demo-rail", "rail", false, [720, 770], 2, [leg("1", "bus", "Kochi Airport", "Aluva", 25, 45, "Take a local bus or cab to Aluva"), leg("2", "rail", "Aluva", "Madurai Junction", 610, 640, "Travel by rail; verify the service and connection", [650, 1100]), leg("3", "auto_cab", "Madurai Junction", "Madurai", 20, 30, "Take an auto-rickshaw to your destination", [250, 350])], [900, 1450], "Rail-led complete journey alternative."),
    candidate("demo-flight", "air", false, [340, 420], 1, [leg("1", "walking", "Kochi Airport", "Departure terminal", 10, 15, "Enter the departure terminal"), leg("2", "air", "Kochi Airport", "Madurai Airport", 70, 85, "Fly to Madurai Airport", [5800, 9200]), leg("3", "auto_cab", "Madurai Airport", "Madurai", 25, 40, "Take a cab to your destination", [700, 1000])], [6500, 10200], "Flight-led complete journey returned by development data."),
  ],
};
