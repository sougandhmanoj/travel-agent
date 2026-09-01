import type { JourneyPlan, Place } from "./types";
import { demoPlan } from "./demo";

const apiBase = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000/api/v1";

export async function searchPlaces(query: string, signal?: AbortSignal): Promise<Place[]> {
  try {
    const response = await fetch(`${apiBase}/places/search?q=${encodeURIComponent(query)}`, { signal });
    if (!response.ok) throw new Error("We couldn’t search places right now. Please try again.");
    return ((await response.json()) as { results: Place[] }).results;
  } catch (reason) {
    if (reason instanceof DOMException && reason.name === "AbortError") throw reason;
    if (reason instanceof Error && reason.message.startsWith("We couldn’t")) throw reason;
    throw new Error("We couldn’t search places right now. Please try again.", { cause: reason });
  }
}

export async function planJourney(originPlaceId: string, destinationPlaceId: string, travelDate: string): Promise<JourneyPlan> {
  try {
    const response = await fetch(`${apiBase}/journeys/plan`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ origin_place_id: originPlaceId, destination_place_id: destinationPlaceId, travel_date: travelDate }) });
    if (!response.ok) {
      const payload = await response.json().catch(() => null) as { detail?: string | { msg?: string }[] } | null;
      const detail = Array.isArray(payload?.detail) ? payload.detail.map((item) => item.msg).filter(Boolean).join(" ") : payload?.detail;
      throw new Error(detail || "We couldn’t plan this journey right now. Please try again.");
    }
    return response.json() as Promise<JourneyPlan>;
  } catch (reason) {
    if (reason instanceof Error && reason.message !== "Failed to fetch" && reason.name !== "TypeError") throw reason;
    throw new Error("We couldn’t plan this journey right now. Please try again.", { cause: reason });
  }
}

// Explicit deterministic fixture for tests and opt-in development previews only.
export const developmentPlan = demoPlan;
