export type Mode = "road" | "rail" | "air";
export type TravelMode = Mode | "metro" | "bus" | "auto_cab" | "walking";

export type Place = {
  place_id: string;
  name: string;
  place_type: string;
  locality_or_city: string;
  state: string;
  code?: string | null;
  latitude: number;
  longitude: number;
  associated_city_id?: string | null;
};

export type Point = { name: string; place_id?: string | null; place_type?: string; locality_or_city?: string; state?: string; code?: string | null; associated_city_id?: string | null; location: { latitude: number; longitude: number } };
export type DurationRange = { minimum_minutes: number; maximum_minutes: number };
export type CostRange = { minimum: number; maximum: number; currency: "INR" };

export type JourneyLeg = {
  leg_id: string;
  role: string;
  mode: TravelMode;
  origin: Point;
  destination: Point;
  duration: DurationRange;
  instructions: string;
  service_name?: string | null;
  service_code?: string | null;
  geometry?: { type: "LineString"; coordinates: [number, number][] } | null;
  cost?: { range: CostRange; basis: "per_person" | "per_vehicle"; description: string } | null;
  intermediate_stops: { name: string; guidance: string }[];
};

export type Candidate = {
  candidate_id: string;
  mode: Mode;
  dominant_mode?: Mode | null;
  status: "available" | "unverified" | "unavailable";
  recommended: boolean;
  display_slot?: string | null;
  position_explanation: string;
  total_duration?: DurationRange | null;
  total_distance_km?: number | null;
  cost?: { total?: CostRange | null; basis?: "per_person" | "per_vehicle"; coverage?: string; explanation?: string; self_drive_total?: CostRange; self_drive_basis?: "per_person" | "per_vehicle"; hired_cab_total?: CostRange | null; hired_cab_basis?: "per_person" | "per_vehicle" } | null;
  legs: JourneyLeg[];
  intermediate_stops?: { name: string; place_id?: string | null; guidance: string }[];
  connections?: { connection_id?: string; kind: "transfer" | "mode_change" | "station_change" | "indicative_wait" | "suggested_buffer"; location_name: string; from_leg_id?: string | null; to_leg_id?: string | null; duration?: DurationRange | null; guidance: string; overnight_possible?: boolean }[];
  transfer_count: number;
  mode_change_count: number;
  station_change_count: number;
  difficulty: string;
  confidence: string;
  geometry?: { type: "LineString"; coordinates: [number, number][] } | null;
  warnings: { code: string; severity: string; message: string }[];
  assumptions: string[];
  sources: { label: string; detail: string; last_checked?: string | null; freshness: string }[];
  verification_requirements: { subject: string; required: boolean; guidance: string }[];
  unavailable_reason?: string | null;
  possible_wait_count?: number;
  suggested_buffer_count?: number;
};

export type JourneyPlan = {
  origin: Point & { place_id: string; code?: string | null };
  destination: Point & { place_id: string; code?: string | null };
  travel_date?: string | null;
  recommended_mode?: Mode | null;
  recommendation_explanation: string;
  candidates: Candidate[];
  developmentPreview?: boolean;
};

export type SavedJourney = {
  id: string;
  savedAt: string;
  candidateId: string;
  plan: JourneyPlan;
};
