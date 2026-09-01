import type { Candidate, JourneyLeg, JourneyPlan } from "./types";

type Coordinate = [number, number];

function legCoordinates(leg: JourneyLeg): Coordinate[] {
  return leg.geometry?.coordinates?.length ? leg.geometry.coordinates : [
    [leg.origin.location.longitude, leg.origin.location.latitude],
    [leg.destination.location.longitude, leg.destination.location.latitude],
  ];
}

export function RouteMap({ plan, candidate, activeLeg }: { plan: JourneyPlan; candidate: Candidate; activeLeg: number }) {
  const segments = candidate.legs.map((leg) => ({
    leg,
    exact: Boolean(leg.geometry?.coordinates?.length),
    coordinates: legCoordinates(leg),
  }));
  const all = segments.flatMap((segment) => segment.coordinates);
  if (!all.length) all.push(
    [plan.origin.location.longitude, plan.origin.location.latitude],
    [plan.destination.location.longitude, plan.destination.location.latitude],
  );
  const longitudes = all.map(([longitude]) => longitude); const latitudes = all.map(([, latitude]) => latitude);
  const minLon = Math.min(...longitudes); const maxLon = Math.max(...longitudes); const minLat = Math.min(...latitudes); const maxLat = Math.max(...latitudes);
  const lonSpan = Math.max(maxLon - minLon, .05); const latSpan = Math.max(maxLat - minLat, .05);
  const project = ([longitude, latitude]: Coordinate) => ({ x: 70 + ((longitude - minLon) / lonSpan) * 640, y: 1390 - ((latitude - minLat) / latSpan) * 1240 });
  const toPath = (coordinates: Coordinate[]) => coordinates.map((coordinate, index) => { const point = project(coordinate); return `${index ? "L" : "M"}${point.x.toFixed(1)} ${point.y.toFixed(1)}`; }).join(" ");
  const activeCoordinate = segments[Math.min(activeLeg, Math.max(segments.length - 1, 0))]?.coordinates.at(-1) ?? all.at(-1)!;
  const pointer = project(activeCoordinate);
  const origin = project(all[0]); const destination = project(all.at(-1)!);
  const completeGeometry = segments.every((segment) => segment.exact || segment.leg.mode === "air");

  return <div className="ws-route-map" aria-label={completeGeometry ? "Journey route map" : "Journey route with schematic sections"} role="img">
    <svg viewBox="0 0 780 1544" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
      <defs><filter id="flight-shadow" x="-30%" y="-30%" width="160%" height="160%"><feDropShadow dx="0" dy="10" stdDeviation="9" floodColor="#173d35" floodOpacity=".2" /></filter></defs>
      <g className="ws-map-grid"><path d="M0 310H780M0 620H780M0 930H780M0 1240H780M156 0V1544M312 0V1544M468 0V1544M624 0V1544" /></g>
      {segments.map(({ leg, coordinates, exact }) => {
        const className = `route ${leg.mode} ${exact || leg.mode === "air" ? "" : "schematic"}`;
        if (leg.mode === "air") {
          const start = project(coordinates[0]); const end = project(coordinates.at(-1)!); const controlX = (start.x + end.x) / 2 + 110; const controlY = Math.min(start.y, end.y) - 150;
          return <path className={className} d={`M${start.x} ${start.y} Q${controlX} ${controlY} ${end.x} ${end.y}`} filter="url(#flight-shadow)" key={leg.leg_id} />;
        }
        return <path className={className} d={toPath(coordinates)} key={leg.leg_id} />;
      })}
      <circle className="endpoint" cx={origin.x} cy={origin.y} r="10" /><circle className="endpoint" cx={destination.x} cy={destination.y} r="10" />
      <g className="route-pointer" style={{ transform: `translate(${pointer.x}px, ${pointer.y}px)` }}><circle r="14" /><circle r="8" /></g>
    </svg>
    {!completeGeometry && <span className="ws-schematic-label">Dashed sections are schematic · verify the exact path</span>}
  </div>;
}
