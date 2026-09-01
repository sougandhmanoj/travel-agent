import type { JourneyPlan, SavedJourney } from "./types";

const key = "waystory.saved-journeys.v1";
const identity = (plan: JourneyPlan, candidateId: string) => [
  plan.origin.place_id,
  plan.destination.place_id,
  plan.travel_date ?? "unscheduled",
  candidateId,
].join(":");

export const savedJourneys = {
  list(): SavedJourney[] { try { return JSON.parse(localStorage.getItem(key) ?? "[]") as SavedJourney[]; } catch { return []; } },
  has(plan: JourneyPlan, candidateId: string) { const id = identity(plan, candidateId); return this.list().some((item) => item.id === id); },
  save(plan: JourneyPlan, candidateId: string) { const id = identity(plan, candidateId); const items = this.list().filter((item) => item.id !== id); items.unshift({ id, savedAt: new Date().toISOString(), candidateId, plan }); localStorage.setItem(key, JSON.stringify(items)); },
  remove(plan: JourneyPlan, candidateId: string) { const id = identity(plan, candidateId); localStorage.setItem(key, JSON.stringify(this.list().filter((item) => item.id !== id))); },
};
