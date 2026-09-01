import { type KeyboardEvent, useEffect, useId, useRef, useState } from "react";

import { searchPlaces } from "./api";
import type { Place } from "./types";

type Props = {
  label: string;
  tone: "origin" | "destination";
  value: string;
  selected: Place | null;
  onValueChange: (value: string) => void;
  onSelect: (place: Place) => void;
  pin: React.ReactNode;
};

export function PlaceCombobox({ label, value, selected, onValueChange, onSelect, pin }: Props) {
  const listId = useId();
  const [results, setResults] = useState<Place[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [active, setActive] = useState(-1);
  const blurTimer = useRef<number | undefined>(undefined);

  useEffect(() => {
    if (selected?.name === value || value.trim().length < 2) { setResults([]); setOpen(false); setLoading(false); setError(""); return; }
    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      setLoading(true); setError("");
      try {
        const places = await searchPlaces(value.trim(), controller.signal);
        setResults(places); setOpen(true); setActive(places.length ? 0 : -1);
      } catch (reason) {
        if ((reason as Error).name !== "AbortError") { setResults([]); setOpen(true); setError((reason as Error).message); }
      } finally { if (!controller.signal.aborted) setLoading(false); }
    }, 250);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [selected, value]);

  function choose(place: Place) { window.clearTimeout(blurTimer.current); onSelect(place); setResults([]); setOpen(false); setActive(-1); setError(""); }
  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "ArrowDown" && results.length) { event.preventDefault(); setOpen(true); setActive((index) => (index + 1) % results.length); }
    if (event.key === "ArrowUp" && results.length) { event.preventDefault(); setOpen(true); setActive((index) => index <= 0 ? results.length - 1 : index - 1); }
    if (event.key === "Enter" && open && active >= 0) { event.preventDefault(); choose(results[active]); }
    if (event.key === "Escape") { setOpen(false); setActive(-1); }
  }

  return (
    <label className="ws-place-field">
      {pin}
      <span className="ws-location-copy">
        <small>{label}</small>
        <input
          aria-label={label}
          aria-autocomplete="list"
          aria-controls={listId}
          aria-expanded={open}
          aria-activedescendant={active >= 0 ? `${listId}-${active}` : undefined}
          autoComplete="off"
          role="combobox"
          value={value}
          placeholder="Search a city or station"
          onChange={(event) => onValueChange(event.target.value)}
          onFocus={() => { if (results.length || error) setOpen(true); }}
          onBlur={() => { blurTimer.current = window.setTimeout(() => setOpen(false), 120); }}
          onKeyDown={onKeyDown}
        />
        {open && <ul className="ws-place-options" id={listId} role="listbox" aria-label={`${label} suggestions`}>
          {loading && <li className="status" role="option" aria-selected="false">Searching supported places…</li>}
          {!loading && error && <li className="status error" role="option" aria-selected="false">{error}</li>}
          {!loading && !error && results.length === 0 && <li className="status" role="option" aria-selected="false">No supported places found.</li>}
          {!loading && results.map((place, index) => <li id={`${listId}-${index}`} role="option" aria-selected={index === active} key={place.place_id} onMouseDown={(event) => event.preventDefault()} onClick={() => choose(place)}>
            <strong>{place.name}{place.code ? ` (${place.code})` : ""}</strong>
            <small>{place.locality_or_city} · {place.state} · {place.place_type.replaceAll("_", " ")}</small>
          </li>)}
        </ul>}
      </span>
    </label>
  );
}
