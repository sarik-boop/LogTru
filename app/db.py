import os, psycopg
from psycopg.rows import dict_row

SCHEMA = """
CREATE TABLE IF NOT EXISTS loads (load text PRIMARY KEY, origin text, destination text, pickup text, delivery text, unit text, rate numeric, source text DEFAULT 'manual');
CREATE TABLE IF NOT EXISTS stations (sid text PRIMARY KEY, name text, city text, st text, lat float, lng float);
CREATE TABLE IF NOT EXISTS prices (sid text REFERENCES stations(sid), seen timestamptz, price float, PRIMARY KEY (sid, seen));
ALTER TABLE stations ADD COLUMN IF NOT EXISTS source text DEFAULT 'airtable';
ALTER TABLE stations ADD COLUMN IF NOT EXISTS geo_state text;
DELETE FROM prices WHERE price <= 1 OR price > 15;   -- bad rows (e.g. $0.00 listings)
UPDATE stations SET source='uf' WHERE sid LIKE 'UF:%' AND source IS DISTINCT FROM 'uf';
-- prices = full history (one row per station per day). current_stations = the ONE clean table the planner uses:
-- latest price per station, ignoring prices older than 14 days, and dropping an Airtable-sourced station
-- when a United Fuel station sits within ~0.3 mi of it (same physical station, UF is the live source).
CREATE OR REPLACE VIEW current_stations AS
SELECT s.sid, s.name, s.city, s.st, s.lat, s.lng, s.source, l.price, l.seen
FROM stations s
JOIN (SELECT DISTINCT ON (sid) sid, seen, price FROM prices ORDER BY sid, seen DESC) l USING (sid)
WHERE s.lat IS NOT NULL AND l.price BETWEEN 1 AND 15 AND l.seen >= now() - interval '14 days'
  AND NOT (s.source <> 'uf' AND EXISTS (SELECT 1 FROM stations u WHERE u.source='uf' AND u.lat IS NOT NULL
           AND abs(u.lat - s.lat) < 0.004 AND abs(u.lng - s.lng) < 0.005));
CREATE TABLE IF NOT EXISTS plans (id serial PRIMARY KEY, load text, created timestamptz DEFAULT now(), result jsonb, sent boolean DEFAULT false);
ALTER TABLE loads ADD COLUMN IF NOT EXISTS broker text;
ALTER TABLE loads ADD COLUMN IF NOT EXISTS broker_load text;
ALTER TABLE loads ADD COLUMN IF NOT EXISTS status text;
ALTER TABLE loads ADD COLUMN IF NOT EXISTS origin_facility text;
ALTER TABLE loads ADD COLUMN IF NOT EXISTS dest_facility text;
ALTER TABLE loads ADD COLUMN IF NOT EXISTS deadhead_mi float;
ALTER TABLE loads ADD COLUMN IF NOT EXISTS loaded_mi float;
ALTER TABLE loads ADD COLUMN IF NOT EXISTS weight_lbs float;
ALTER TABLE loads ADD COLUMN IF NOT EXISTS truck text;
ALTER TABLE loads ADD COLUMN IF NOT EXISTS assign_info jsonb;
CREATE TABLE IF NOT EXISTS trucks (unit text PRIMARY KEY, driver text, city text, st text, lat float, lng float, free_at timestamptz);
CREATE TABLE IF NOT EXISTS fuel_txns (key text PRIMARY KEY, tdate date NOT NULL, txn text, equip text, driver text, merchant text, city text, st text,
  gallons float, ppg float, diesel_amt float, def_amt float, fee float, total float, discount float, paid float, imported timestamptz DEFAULT now());
CREATE INDEX IF NOT EXISTS fuel_txns_equip_date ON fuel_txns(equip, tdate);
CREATE TABLE IF NOT EXISTS done_loads (trip text PRIMARY KEY, status text, bill_to text, origin text, dest text, o_time text, d_time text,
  pickup date, delivery date, empty_mi float, loaded_mi float, rate float, truck text, driver text, updated timestamptz DEFAULT now());
CREATE TABLE IF NOT EXISTS geo (q text PRIMARY KEY, lat float, lng float);
"""

def conn():
    return psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row, autocommit=True)

def init():
    with conn() as c: c.execute(SCHEMA)
