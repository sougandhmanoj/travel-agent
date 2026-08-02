begin;

create extension if not exists pgtap with schema extensions;
set local search_path = public, extensions;

select plan(22);

select has_table('public', 'cities', 'cities table exists');
select has_table('public', 'transport_hubs', 'transport_hubs table exists');
select has_table('public', 'import_batches', 'import_batches table exists');

select is((select count(*) from public.cities), 158::bigint, '158 cities were imported');
select is((select count(*) from public.transport_hubs), 500::bigint, '500 hubs were imported');
select is((select count(*) from public.transport_hubs where hub_type = 'Airport'), 20::bigint, '20 airports were imported');
select is((select count(*) from public.transport_hubs where hub_type = 'Railway station'), 180::bigint, '180 railway stations were imported');
select is((select count(*) from public.transport_hubs where hub_type = 'Bus terminal'), 151::bigint, '151 bus terminals were imported');
select is((select count(*) from public.transport_hubs where hub_type = 'Metro station'), 149::bigint, '149 metro stations were imported');

select is(
    (select count(*) from public.transport_hubs h left join public.cities c using (city_id) where c.city_id is null),
    0::bigint,
    'every hub references an imported city'
);
select is((select count(*) - count(distinct city_id) from public.cities), 0::bigint, 'city IDs are unique');
select is((select count(*) - count(distinct hub_id) from public.transport_hubs), 0::bigint, 'hub IDs are unique');
select is((select count(distinct state) from public.cities), 4::bigint, 'all four launch states are represented');
select is((select count(*) from public.cities where last_verified is null), 0::bigint, 'every city has a verification date');
select is((select count(*) from public.transport_hubs where last_verified is null), 0::bigint, 'every hub has a verification date');
select is((select count(*) from public.import_batches where validation_status = 'passed'), 1::bigint, 'the workbook import audit passed');
select is(
    (select source_sha256 from public.import_batches limit 1),
    '0034f2f33195c8223859e7ef50eb29bb58f67f7ce39736e09b9b21f5a3e38a7b',
    'the import audit records the verified workbook hash'
);
select hasnt_table('public', 'import_staging_cities', 'city staging is removed after import');
select hasnt_table('public', 'import_staging_transport_hubs', 'hub staging is removed after import');
select ok((select relrowsecurity from pg_class where oid = 'public.cities'::regclass), 'cities has RLS enabled');
select ok((select relrowsecurity from pg_class where oid = 'public.transport_hubs'::regclass), 'transport_hubs has RLS enabled');
select ok((select relrowsecurity from pg_class where oid = 'public.import_batches'::regclass), 'import audit has RLS enabled');

select * from finish();
rollback;
