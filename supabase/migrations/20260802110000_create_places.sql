begin;

-- Keep updated_at accurate whenever an existing row changes.
create or replace function public.set_updated_at()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

-- Cities and localities that users can select in search.
create table public.cities (
    city_id text primary key
        check (city_id ~ '^[a-z0-9_]+$'),

    city_name text not null
        check (char_length(trim(city_name)) between 1 and 200),

    state text not null
        check (state in ('Goa', 'Karnataka', 'Kerala', 'Tamil Nadu')),

    latitude double precision not null
        check (latitude between -90 and 90),

    longitude double precision not null
        check (longitude between -180 and 180),

    priority text not null default 'A',
    coverage_status text not null default 'MVP',
    notes text,
    source_url text,
    last_verified date,

    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

-- Airports, railway stations, bus terminals, and metro stations.
create table public.transport_hubs (
    hub_id text primary key
        check (hub_id ~ '^[a-z0-9_]+$'),

    city_id text not null
        references public.cities (city_id)
        on update cascade
        on delete restrict,

    hub_name text not null
        check (char_length(trim(hub_name)) between 1 and 200),

    hub_type text not null
        check (
            hub_type in (
                'Airport',
                'Railway station',
                'Bus terminal',
                'Metro station'
            )
        ),

    hub_subtype text,
    code text
        check (code is null or char_length(trim(code)) between 1 and 20),

    latitude double precision not null
        check (latitude between -90 and 90),

    longitude double precision not null
        check (longitude between -180 and 180),

    area_or_locality text,
    priority text not null default 'A',
    use_in_mvp boolean not null default true,

    confidence text not null default 'High'
        check (confidence in ('High', 'Medium', 'Low')),

    source_primary text,
    source_url text,
    last_verified date,
    notes text,

    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

-- Every workbook load is recorded so its source and validation result remain
-- auditable after the staging tables are discarded.
create table public.import_batches (
    batch_id bigint generated always as identity primary key,
    source_filename text not null,
    source_sha256 text not null
        check (source_sha256 ~ '^[0-9a-f]{64}$'),
    expected_city_count integer not null check (expected_city_count >= 0),
    expected_hub_count integer not null check (expected_hub_count >= 0),
    imported_city_count integer not null check (imported_city_count >= 0),
    imported_hub_count integer not null check (imported_hub_count >= 0),
    validation_status text not null
        check (validation_status in ('passed', 'failed')),
    validation_results jsonb not null default '{}'::jsonb,
    imported_at timestamptz not null default now(),
    unique (source_sha256)
);

-- These indexes make common place-search and relationship queries faster.
create index cities_name_idx
    on public.cities (lower(city_name));

create index transport_hubs_name_idx
    on public.transport_hubs (lower(hub_name));

create index transport_hubs_city_id_idx
    on public.transport_hubs (city_id);

create index transport_hubs_type_idx
    on public.transport_hubs (hub_type);

-- Automatically refresh updated_at when a row changes.
create trigger cities_set_updated_at
before update on public.cities
for each row
execute function public.set_updated_at();

create trigger transport_hubs_set_updated_at
before update on public.transport_hubs
for each row
execute function public.set_updated_at();

-- Row Level Security prevents writes through public API keys.
alter table public.cities enable row level security;
alter table public.transport_hubs enable row level security;
alter table public.import_batches enable row level security;

-- The application may read MVP places using Supabase's public roles.
grant select on public.cities to anon, authenticated;
grant select on public.transport_hubs to anon, authenticated;

create policy cities_public_read
on public.cities
for select
to anon, authenticated
using (coverage_status = 'MVP');

create policy transport_hubs_public_read
on public.transport_hubs
for select
to anon, authenticated
using (use_in_mvp = true);

commit;
