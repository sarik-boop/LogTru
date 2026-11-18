import os, psycopg
from psycopg.rows import dict_row

SCHEMA = """
CREATE TABLE IF NOT EXISTS loads (load text PRIMARY KEY, origin text, destination text, pickup text, delivery text, unit text, rate numeric, source text DEFAULT 'manual');
CREATE TABLE IF NOT EXISTS stations (sid text PRIMARY KEY, name text, city text, st text, lat float, lng float);
CREATE TABLE IF NOT EXISTS prices (sid text REFERENCES stations(sid), seen timestamptz, price float, PRIMARY KEY (sid, seen));
ALTER TABLE stations ADD COLUMN IF NOT EXISTS source text DEFAULT 'airtable';
UPDATE stations SET source='uf' WHERE sid LIKE 'UF:%' AND source IS DISTINCT FROM 'uf';
-- prices = full history (one row per station per day). current_stations = the ONE clean table the planner uses:
-- latest price per station, ignoring prices older than 14 days, and dropping an Airtable-sourced station
-- when a United Fuel station sits within ~0.3 mi of it (same physical station, UF is the live source).
CREATE OR REPLACE VIEW current_stations AS
SELECT s.sid, s.name, s.city, s.st, s.lat, s.lng, s.source, l.price, l.seen
FROM stations s
JOIN (SELECT DISTINCT ON (sid) sid, seen, price FROM prices ORDER BY sid, seen DESC) l USING (sid)
WHERE s.lat IS NOT NULL AND l.seen >= now() - interval '14 days'
  AND NOT (s.source <> 'uf' AND EXISTS (SELECT 1 FROM stations u WHERE u.source='uf' AND u.lat IS NOT NULL
           AND abs(u.lat - s.lat) < 0.004 AND abs(u.lng - s.lng) < 0.005));
CREATE TABLE IF NOT EXISTS plans (id serial PRIMARY KEY, load text, created timestamptz DEFAULT now(), result jsonb, sent boolean DEFAULT false);
"""

def conn():
    return psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row, autocommit=True)

def init():
    with conn() as c: c.execute(SCHEMA)
