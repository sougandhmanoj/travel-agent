import crypto from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.resolve(scriptDirectory, "..");
const workbookPath = path.join(
  projectRoot,
  "outputs/south_india_hubs_workbook/south_india_mvp_final_verified.xlsx",
);
const seedPath = path.join(projectRoot, "supabase/seed.sql");

const EXPECTED_CITY_COUNT = 158;
const EXPECTED_HUB_COUNT = 500;
const EXPECTED_MODE_COUNTS = new Map([
  ["Airport", 20],
  ["Railway station", 180],
  ["Bus terminal", 151],
  ["Metro station", 149],
]);
const ALLOWED_STATES = new Set(["Goa", "Karnataka", "Kerala", "Tamil Nadu"]);
const CITY_HEADERS = [
  "city_id",
  "city_name",
  "state",
  "latitude",
  "longitude",
  "priority",
  "coverage_status",
  "notes",
  "source_url",
  "last_verified",
];
const HUB_HEADERS = [
  "hub_id",
  "city_id",
  "city_name",
  "state",
  "hub_name",
  "hub_type",
  "hub_subtype",
  "code",
  "latitude",
  "longitude",
  "area_or_locality",
  "priority",
  "use_in_mvp",
  "confidence",
  "source_primary",
  "source_url",
  "last_verified",
  "notes",
];

function fail(message) {
  throw new Error(`Workbook validation failed: ${message}`);
}

function assert(condition, message) {
  if (!condition) fail(message);
}

function rowsToObjects(values, expectedHeaders, sheetName) {
  assert(values.length > 1, `${sheetName} has no data rows`);
  const headers = values[0].map(String);
  assert(
    JSON.stringify(headers) === JSON.stringify(expectedHeaders),
    `${sheetName} headers do not match the verified schema`,
  );
  return values.slice(1).map((row) =>
    Object.fromEntries(expectedHeaders.map((header, index) => [header, row[index] ?? null])),
  );
}

function validateCoordinates(row, label) {
  assert(typeof row.latitude === "number", `${label} latitude is not numeric`);
  assert(typeof row.longitude === "number", `${label} longitude is not numeric`);
  assert(row.latitude >= -90 && row.latitude <= 90, `${label} latitude is out of range`);
  assert(
    row.longitude >= -180 && row.longitude <= 180,
    `${label} longitude is out of range`,
  );
}

function excelDateToIso(value, label) {
  if (typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value)) return value;
  assert(typeof value === "number" && Number.isFinite(value), `${label} has an invalid date`);
  const epoch = Date.UTC(1899, 11, 30);
  return new Date(epoch + Math.round(value) * 86_400_000).toISOString().slice(0, 10);
}

function sqlValue(value) {
  if (value === null || value === undefined || value === "") return "null";
  if (typeof value === "number") return String(value);
  if (typeof value === "boolean") return value ? "true" : "false";
  return `'${String(value).replaceAll("'", "''")}'`;
}

function valuesBlock(rows, columns) {
  return rows
    .map((row) => `    (${columns.map((column) => sqlValue(row[column])).join(", ")})`)
    .join(",\n");
}

function validateAndNormalize(cities, hubs) {
  assert(cities.length === EXPECTED_CITY_COUNT, `expected 158 cities, found ${cities.length}`);
  assert(hubs.length === EXPECTED_HUB_COUNT, `expected 500 hubs, found ${hubs.length}`);

  const cityIds = new Set();
  const cityById = new Map();
  for (const city of cities) {
    const label = `city ${city.city_id}`;
    assert(/^[a-z0-9_]+$/.test(city.city_id), `${label} has an invalid stable ID`);
    assert(!cityIds.has(city.city_id), `${label} is duplicated`);
    assert(ALLOWED_STATES.has(city.state), `${label} has an unsupported state`);
    assert(String(city.city_name).trim().length > 0, `${label} has no name`);
    assert(city.coverage_status === "MVP", `${label} is not marked MVP`);
    validateCoordinates(city, label);
    city.last_verified = excelDateToIso(city.last_verified, label);
    cityIds.add(city.city_id);
    cityById.set(city.city_id, city);
  }

  const hubIds = new Set();
  const modeCounts = new Map();
  for (const hub of hubs) {
    const label = `hub ${hub.hub_id}`;
    assert(/^[a-z0-9_]+$/.test(hub.hub_id), `${label} has an invalid stable ID`);
    assert(!hubIds.has(hub.hub_id), `${label} is duplicated`);
    const parentCity = cityById.get(hub.city_id);
    assert(parentCity, `${label} references missing city ${hub.city_id}`);
    assert(hub.city_name === parentCity.city_name, `${label} city name disagrees with its city`);
    assert(hub.state === parentCity.state, `${label} state disagrees with its city`);
    assert(EXPECTED_MODE_COUNTS.has(hub.hub_type), `${label} has an unsupported type`);
    assert(String(hub.hub_name).trim().length > 0, `${label} has no name`);
    assert(["High", "Medium", "Low"].includes(hub.confidence), `${label} confidence is invalid`);
    assert(["Yes", "No", true, false].includes(hub.use_in_mvp), `${label} MVP flag is invalid`);
    validateCoordinates(hub, label);
    hub.use_in_mvp = hub.use_in_mvp === "Yes" || hub.use_in_mvp === true;
    const normalizedCode = hub.code === null ? "" : String(hub.code).trim();
    if (normalizedCode.length > 20) {
      assert(
        hub.hub_id === "hub_00748" && hub.hub_type === "Bus terminal",
        `${label} contains unexpected free text in the code field`,
      );
      hub.code = null;
    } else {
      hub.code = normalizedCode === "" ? null : normalizedCode;
    }
    hub.last_verified = excelDateToIso(hub.last_verified, label);
    hubIds.add(hub.hub_id);
    modeCounts.set(hub.hub_type, (modeCounts.get(hub.hub_type) ?? 0) + 1);
  }

  for (const [mode, expectedCount] of EXPECTED_MODE_COUNTS) {
    assert(modeCounts.get(mode) === expectedCount, `${mode} count is not ${expectedCount}`);
  }
}

const workbookBytes = await fs.readFile(workbookPath);
const sourceSha256 = crypto.createHash("sha256").update(workbookBytes).digest("hex");
const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(workbookPath));
const cities = rowsToObjects(
  workbook.worksheets.getItem("Cities").getRange("A1:J159").values,
  CITY_HEADERS,
  "Cities",
);
const hubs = rowsToObjects(
  workbook.worksheets.getItem("Transport_Hubs").getRange("A1:R501").values,
  HUB_HEADERS,
  "Transport_Hubs",
);

validateAndNormalize(cities, hubs);

const cityColumns = [
  "city_id",
  "city_name",
  "state",
  "latitude",
  "longitude",
  "priority",
  "coverage_status",
  "notes",
  "source_url",
  "last_verified",
];
const hubColumns = [
  "hub_id",
  "city_id",
  "hub_name",
  "hub_type",
  "hub_subtype",
  "code",
  "latitude",
  "longitude",
  "area_or_locality",
  "priority",
  "use_in_mvp",
  "confidence",
  "source_primary",
  "source_url",
  "last_verified",
  "notes",
];

const seedSql = `-- Generated by scripts/generate_supabase_seed.mjs.
-- Source: south_india_mvp_final_verified.xlsx
-- SHA-256: ${sourceSha256}
-- Do not edit this file by hand; regenerate it from the verified workbook.

do $seed$
begin

create table public.import_staging_cities
(like public.cities including defaults);

create table public.import_staging_transport_hubs
(like public.transport_hubs including defaults);

insert into public.import_staging_cities (${cityColumns.join(", ")}) values
${valuesBlock(cities, cityColumns)};

insert into public.import_staging_transport_hubs (${hubColumns.join(", ")}) values
${valuesBlock(hubs, hubColumns)};

    if (select count(*) from public.import_staging_cities) <> ${EXPECTED_CITY_COUNT} then
        raise exception 'City staging count must be ${EXPECTED_CITY_COUNT}';
    end if;
    if (select count(*) from public.import_staging_transport_hubs) <> ${EXPECTED_HUB_COUNT} then
        raise exception 'Hub staging count must be ${EXPECTED_HUB_COUNT}';
    end if;
    if exists (
        select city_id from public.import_staging_cities group by city_id having count(*) > 1
    ) then
        raise exception 'Duplicate city IDs found in staging';
    end if;
    if exists (
        select hub_id from public.import_staging_transport_hubs group by hub_id having count(*) > 1
    ) then
        raise exception 'Duplicate hub IDs found in staging';
    end if;
    if exists (
        select 1
        from public.import_staging_transport_hubs h
        left join public.import_staging_cities c using (city_id)
        where c.city_id is null
    ) then
        raise exception 'A transport hub references a missing city';
    end if;

insert into public.cities (${cityColumns.join(", ")})
select ${cityColumns.join(", ")} from public.import_staging_cities;

insert into public.transport_hubs (${hubColumns.join(", ")})
select ${hubColumns.join(", ")} from public.import_staging_transport_hubs;

insert into public.import_batches (
    source_filename,
    source_sha256,
    expected_city_count,
    expected_hub_count,
    imported_city_count,
    imported_hub_count,
    validation_status,
    validation_results
) values (
    'south_india_mvp_final_verified.xlsx',
    '${sourceSha256}',
    ${EXPECTED_CITY_COUNT},
    ${EXPECTED_HUB_COUNT},
    (select count(*) from public.import_staging_cities),
    (select count(*) from public.import_staging_transport_hubs),
    'passed',
    jsonb_build_object(
        'states', 4,
        'airports', 20,
        'railway_stations', 180,
        'bus_terminals', 151,
        'metro_stations', 149,
        'normalized_fields', jsonb_build_array('hub_00748.code: free text converted to null')
    )
);

drop table public.import_staging_transport_hubs;
drop table public.import_staging_cities;
end;
$seed$;
`;

await fs.writeFile(seedPath, seedSql, "utf8");
console.log(`Validated ${cities.length} cities and ${hubs.length} hubs.`);
console.log(`Workbook SHA-256: ${sourceSha256}`);
console.log(`Wrote ${path.relative(projectRoot, seedPath)}.`);
