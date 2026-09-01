import type { Candidate, JourneyPlan } from "./types";

export type DesignMode = "recommended" | "road" | "rail" | "flight";

export type ResultDesign = {
  id: DesignMode;
  label: string;
  subtitle: string;
  title: string;
  description: string;
  duration: string;
  cost: string;
  transfers: string;
  image: string;
};

export const resultDesigns: ResultDesign[] = [
  { id: "recommended", label: "Recommended", subtitle: "Best overall", title: "Rail via Ernakulam", description: "Best balance of certainty, comfort and cost.", duration: "11h 25m", cost: "₹1,900–₹2,600", transfers: "2 changes", image: "coastal-train.png" },
  { id: "road", label: "Road", subtitle: "Fewest changes", title: "Direct road journey", description: "Door-to-door by road with a planned comfort stop.", duration: "7h 45m–9h", cost: "₹5,500–₹7,500", transfers: "No changes", image: "coastal-cab.png" },
  { id: "rail", label: "Rail", subtitle: "Lowest estimated cost", title: "Rail journey", description: "A rail-led journey with local connections at each end.", duration: "12h 10m", cost: "₹1,300–₹2,100", transfers: "2 changes", image: "coastal-train.png" },
  { id: "flight", label: "Flight", subtitle: "Shortest travel time", title: "Flight journey", description: "Airport access, flight and final road connection.", duration: "5h 40m–7h", cost: "₹6,500–₹10,500", transfers: "1 connection", image: "coastal-plane.png" },
];

export type JourneyStepDesign = {
  mode: string;
  title: string;
  meta: string;
  detail?: string;
};

export type JourneyDesign = {
  id: DesignMode;
  eyebrow: string;
  summary: string;
  active: number;
  counter: string;
  viewing: string;
  action: string;
  map: string;
  steps: JourneyStepDesign[];
};

const commonArrival: JourneyStepDesign = { mode: "ARRIVAL", title: "Arrive at your door", meta: "2–5 min · Journey complete" };

export const journeyDesigns: Record<DesignMode, JourneyDesign> = {
  recommended: {
    id: "recommended", eyebrow: "RECOMMENDED JOURNEY", summary: "11h 25m · ₹1,900–₹2,600 · 2 changes", active: 3, counter: "4 / 7", viewing: "Verify the train", action: "Check availability", map: "rail-map.png",
    steps: [
      { mode: "ROAD", title: "Cab to Ernakulam Junction", meta: "45–65 min · ₹700–₹1,000" },
      { mode: "WALK", title: "Enter Ernakulam Junction", meta: "8–12 min · Main entrance" },
      { mode: "RAIL", title: "Find your platform", meta: "8–12 min · 35 min buffer" },
      { mode: "RAIL", title: "Train to Madurai Junction", meta: "Approx. 9h 40m · ₹1,000–₹1,400", detail: "Your seat must be reserved. Keep the ticket and identification accessible, then verify the final platform before leaving Kochi." },
      { mode: "WALK", title: "Exit to the auto stand", meta: "5–8 min · Main concourse" },
      { mode: "ROAD", title: "Auto-rickshaw to destination", meta: "20–30 min · ₹250–₹350", detail: "Use the official stand and agree the fare before starting." },
      { ...commonArrival, mode: "WALK" },
    ],
  },
  road: {
    id: "road", eyebrow: "ROAD JOURNEY", summary: "7h 45m–9h · ₹5,500–₹7,500 · 1 planned stop", active: 4, counter: "5 / 6", viewing: "Final drive to Madurai", action: "Check live traffic", map: "road-map.png",
    steps: [
      { mode: "ROAD", title: "Meet your cab", meta: "10–20 min · Airport pickup zone" },
      { mode: "ROAD", title: "Leave Kochi Airport", meta: "Approx. 1h 30m · Traffic dependent" },
      { mode: "ROAD", title: "Continue through Palakkad", meta: "Approx. 2h · Tolls may apply" },
      { mode: "STOP", title: "Comfort stop near Palakkad", meta: "20–30 min · Food and washrooms" },
      { mode: "ROAD", title: "Continue to Madurai via Dindigul", meta: "Approx. 4h 15m · ₹5,500–₹7,500", detail: "Traffic can vary near Dindigul and on the final approach. Keep a short arrival buffer and confirm tolls are included before continuing." },
      { ...commonArrival, meta: "20–30 min · Journey complete" },
    ],
  },
  rail: {
    id: "rail", eyebrow: "RAIL JOURNEY", summary: "12h 10m · ₹1,300–₹2,100 · 2 changes", active: 3, counter: "4 / 7", viewing: "Train to Madurai Junction", action: "Check train status", map: "rail-map.png",
    steps: [
      { mode: "ROAD", title: "Airport bus or cab to Aluva", meta: "25–45 min · Traffic dependent" },
      { mode: "RAIL", title: "Local train connection", meta: "Allow a 30 min station buffer" },
      { mode: "RAIL", title: "Find your platform and coach", meta: "35–50 min · Recommended buffer" },
      { mode: "RAIL", title: "Train to Madurai Junction", meta: "Approx. 10h 15m · ₹650–₹1,100", detail: "This option keeps the estimated cost lowest, but the train does most of the work. Keep your ticket and ID accessible, verify the final platform, and check the live running status before leaving for the station." },
      { mode: "WALK", title: "Exit to the auto stand", meta: "5–8 min · Main concourse" },
      { mode: "ROAD", title: "Auto-rickshaw to destination", meta: "20–30 min · ₹250–₹350" },
      commonArrival,
    ],
  },
  flight: {
    id: "flight", eyebrow: "FLIGHT JOURNEY", summary: "5h 40m–7h · ₹6,500–₹10,500 · fastest", active: 3, counter: "4 / 7", viewing: "Flight to Madurai Airport", action: "Check flight status", map: "flight-map.png",
    steps: [
      { mode: "WALK", title: "Enter the departure terminal", meta: "8–12 min · Domestic departures" },
      { mode: "AIRPORT", title: "Check in and clear security", meta: "Approx. 2h · Suggested buffer" },
      { mode: "GATE", title: "Reach the boarding gate", meta: "20–35 min · Gate may change" },
      { mode: "FLIGHT", title: "Fly to Madurai Airport", meta: "Approx. 1h 10m · ₹5,800–₹9,200", detail: "The flight is the shortest main segment, but airport buffers matter most. Keep your boarding pass and ID ready, then confirm the gate and live departure status before security." },
      { mode: "AIRPORT", title: "Collect baggage and exit", meta: "20–40 min · Arrivals hall" },
      { mode: "ROAD", title: "Cab to destination", meta: "25–40 min · ₹700–₹1,000" },
      commonArrival,
    ],
  },
};

export function designIdForCandidate(candidate: Candidate): DesignMode {
  if (candidate.recommended) return "recommended";
  return candidate.mode === "air" ? "flight" : candidate.mode;
}

export function modeDesignIdForCandidate(candidate: Candidate): Exclude<DesignMode, "recommended"> {
  return candidate.mode === "air" ? "flight" : candidate.mode;
}

export function candidateForDesign(plan: JourneyPlan, id: DesignMode): Candidate | undefined {
  return plan.candidates.find((candidate) => designIdForCandidate(candidate) === id);
}
