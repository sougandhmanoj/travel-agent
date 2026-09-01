import { describe, expect, it } from "vitest";
import { developmentPlan } from "./api";
import { savedJourneys } from "./storage";

describe("saved journeys repository", () => {
  it("saves, replaces and removes a journey without duplicating it", () => {
    const id = developmentPlan.candidates[0].candidate_id;
    savedJourneys.save(developmentPlan, id);
    savedJourneys.save(developmentPlan, id);
    expect(savedJourneys.list()).toHaveLength(1);
    expect(savedJourneys.has(developmentPlan, id)).toBe(true);
    savedJourneys.remove(developmentPlan, id);
    expect(savedJourneys.list()).toEqual([]);
  });

  it("keeps the same candidate id separate across different routes", () => {
    const candidateId = developmentPlan.candidates[0].candidate_id;
    const anotherPlan = {
      ...developmentPlan,
      origin: { ...developmentPlan.origin, place_id: "kerala_kannur", name: "Kannur" },
    };
    savedJourneys.save(developmentPlan, candidateId);
    savedJourneys.save(anotherPlan, candidateId);
    expect(savedJourneys.list()).toHaveLength(2);
  });
});
