import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { BrowserRouter } from "react-router-dom";
import axe from "axe-core";

import App from "./App";
import { developmentPlan } from "./api";
import type { JourneyPlan, Place } from "./types";

const kannur: Place = { place_id: "kerala_kannur", name: "Kannur", place_type: "locality", locality_or_city: "Kannur", state: "Kerala", latitude: 11.8745, longitude: 75.3704 };
const kochi: Place = { place_id: "kerala_kochi", name: "Kochi", place_type: "locality", locality_or_city: "Kochi", state: "Kerala", latitude: 9.9312, longitude: 76.2673 };

function dynamicPlan(): JourneyPlan {
  const plan = structuredClone(developmentPlan);
  delete plan.developmentPreview;
  plan.origin = { ...plan.origin, name: "Kannur", place_id: kannur.place_id, location: { latitude: kannur.latitude, longitude: kannur.longitude } };
  plan.destination = { ...plan.destination, name: "Kochi", place_id: kochi.place_id, location: { latitude: kochi.latitude, longitude: kochi.longitude } };
  plan.travel_date = "2026-09-12";
  const recommended = plan.candidates[0];
  recommended.candidate_id = "live-recommended";
  recommended.legs[0].origin.name = "Kannur";
  const railLeg = recommended.legs.find((leg) => leg.mode === "rail");
  if (railLeg) {
    railLeg.instructions = "Board train 22633, Trivandrum Central - Hazrat Nizamuddin SF Express, at Kannur at 23:40; remain onboard to Madgaon Junction, arriving at 07:50.";
    railLeg.service_name = "Trivandrum Central - Hazrat Nizamuddin SF Express";
    railLeg.service_code = "22633";
    railLeg.destination.name = "Madgaon Junction";
  }
  recommended.legs[0].intermediate_stops = [{ name: "Thalassery", guidance: "Remain onboard." }];
  recommended.connections = [{ connection_id: "change-1", kind: "mode_change", location_name: "Ernakulam Junction", from_leg_id: recommended.legs[0].leg_id, to_leg_id: recommended.legs[1].leg_id, duration: { minimum_minutes: 15, maximum_minutes: 25 }, guidance: "Walk to the confirmed platform." }];
  const road = plan.candidates[1];
  road.candidate_id = "live-road";
  road.status = "unavailable";
  road.unavailable_reason = "No defensible road estimate was returned.";
  road.legs = [];
  road.warnings = [];
  const flight = plan.candidates[3];
  flight.candidate_id = "live-flight";
  flight.status = "unavailable";
  flight.unavailable_reason = "No supported flight was returned.";
  plan.candidates = [recommended, road, flight];
  return plan;
}

const renderApp = () => render(<BrowserRouter><App /></BrowserRouter>);
const response = (body: unknown, ok = true, status = 200) => Promise.resolve({ ok, status, json: () => Promise.resolve(body) } as Response);

beforeEach(() => {
  vi.restoreAllMocks();
  window.history.pushState({}, "", "/");
});

describe("Waystory frontend", () => {
  it("renders an empty accessible planner and validates selected suggestions", () => {
    renderApp();
    expect(screen.getByRole("heading", { name: /know the whole journey/i })).toBeInTheDocument();
    expect(screen.getByLabelText("From")).toHaveValue("");
    fireEvent.click(screen.getByRole("button", { name: "Plan my journey" }));
    expect(screen.getByRole("alert")).toHaveTextContent(/select both locations/i);
  });

  it("searches supported places, plans through the API and renders the returned route", async () => {
    const plan = dynamicPlan();
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("places/search") && url.toLowerCase().includes("kannur")) return response({ results: [kannur] });
      if (url.includes("places/search") && url.toLowerCase().includes("kochi")) return response({ results: [kochi] });
      return response(plan);
    }));
    const user = userEvent.setup();
    renderApp();
    await user.type(screen.getByLabelText("From"), "Kannur");
    await user.click(await screen.findByRole("option", { name: /Kannur Kannur · Kerala/i }, { timeout: 1500 }));
    await user.type(screen.getByLabelText("To"), "Kochi");
    await user.click(await screen.findByRole("option", { name: /Kochi Kochi · Kerala/i }, { timeout: 1500 }));
    await user.click(screen.getByRole("button", { name: "Plan my journey" }));
    expect(await screen.findByRole("heading", { name: /Kannur.*Kochi/i })).toBeInTheDocument();
    expect(window.location.pathname).toBe("/results");
    expect(screen.queryByText("Kochi Airport")).not.toBeInTheDocument();
  });

  it("shows an error and does not navigate when planning fails", async () => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("places/search") && url.toLowerCase().includes("kannur")) return response({ results: [kannur] });
      if (url.includes("places/search") && url.toLowerCase().includes("kochi")) return response({ results: [kochi] });
      return response({ detail: "Journey providers are temporarily unavailable." }, false, 503);
    }));
    const user = userEvent.setup();
    renderApp();
    await user.type(screen.getByLabelText("From"), "Kannur");
    await user.click(await screen.findByRole("option", { name: /Kannur Kannur · Kerala/i }, { timeout: 1500 }));
    await user.type(screen.getByLabelText("To"), "Kochi");
    await user.click(await screen.findByRole("option", { name: /Kochi Kochi · Kerala/i }, { timeout: 1500 }));
    await user.click(screen.getByRole("button", { name: "Plan my journey" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Journey providers are temporarily unavailable.");
    expect(window.location.pathname).toBe("/");
  });

  it("uses candidate-specific expanded content, includes unavailable road and omits unavailable flight", () => {
    const plan = dynamicPlan();
    sessionStorage.setItem("waystory.current-plan", JSON.stringify(plan));
    window.history.pushState({}, "", "/results");
    renderApp();
    expect(screen.getByText("No defensible road estimate was returned.")).toBeInTheDocument();
    expect(screen.queryByText("No supported flight was returned.")).not.toBeInTheDocument();
    const recommended = screen.getByRole("button", { name: /Recommended/i });
    const road = screen.getByRole("button", { name: /Road/i });
    fireEvent.click(recommended);
    expect(recommended).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText(/Stay onboard at: Thalassery/i)).toBeInTheDocument();
    expect(screen.getByText(/Selected · Recommended/i)).toBeInTheDocument();
    fireEvent.click(road);
    expect(recommended).toHaveAttribute("aria-expanded", "false");
    expect(road).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText(/Waystory will not invent missing route information/i)).toBeInTheDocument();
  });

  it("builds a dynamic timeline from legs, intermediate stops and connections", () => {
    const plan = dynamicPlan();
    sessionStorage.setItem("waystory.current-plan", JSON.stringify(plan));
    window.history.pushState({}, "", "/journey/live-recommended");
    renderApp();
    expect(screen.getByRole("img", { name: "Journey route with schematic sections" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Thalassery" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Train 22633 to Madgaon Junction" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /Trivandrum Central/i })).not.toBeInTheDocument();
    expect(screen.getByText("Walk to the confirmed platform.")).toBeInTheDocument();
    expect(screen.getByText(/IRCTC does not publish a stable supported prefill URL/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Save journey" }));
    expect(screen.getByRole("button", { name: "Remove saved journey" })).toHaveAttribute("aria-pressed", "true");
  });

  it("renders honest missing-plan and empty-results states", () => {
    window.history.pushState({}, "", "/results");
    const first = renderApp();
    expect(screen.getByRole("heading", { name: "Plan a journey first." })).toBeInTheDocument();
    first.unmount();
    const plan = dynamicPlan(); plan.candidates = []; plan.recommendation_explanation = "Provider evidence was insufficient.";
    sessionStorage.setItem("waystory.current-plan", JSON.stringify(plan));
    renderApp();
    expect(screen.getByRole("heading", { name: /No trustworthy journey/i })).toBeInTheDocument();
    expect(screen.getByText("Provider evidence was insufficient.")).toBeInTheDocument();
  });

  it("has no automatically detectable accessibility violations on home and results", async () => {
    const home = renderApp();
    expect((await axe.run(home.container, { rules: { "color-contrast": { enabled: false } } })).violations).toEqual([]);
    home.unmount();
    sessionStorage.setItem("waystory.current-plan", JSON.stringify(dynamicPlan()));
    window.history.pushState({}, "", "/results");
    const results = renderApp();
    await waitFor(() => expect(screen.getByLabelText("Journey results")).toBeInTheDocument());
    expect((await axe.run(results.container, { rules: { "color-contrast": { enabled: false } } })).violations).toEqual([]);
  });

  it("opens and closes the accessible menu", () => {
    renderApp();
    const button = screen.getByRole("button", { name: "Open menu" });
    fireEvent.click(button);
    expect(screen.getByRole("dialog", { name: "Menu" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Close menu" })).toHaveAttribute("aria-expanded", "true");
  });
});
