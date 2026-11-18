import os, psycopg
from psycopg.rows import dict_row

SCHEMA = """
CREATE TABLE IF NOT EXISTS loads (load text PRIMARY KEY, origin text, destination text, pickup text, delivery text, unit text, rate numeric, source text DEFAULT 'manual');
CREATE TABLE IF NOT EXISTS stations (sid text PRIMARY KEY, name text, city text, st text, lat float, lng float);
CREATE TABLE IF NOT EXISTS prices (sid text REFERENCES stations(sid), seen timestamptz, price float, PRIMARY KEY (sid, seen));
CREATE TABLE IF NOT EXISTS plans (id serial PRIMARY KEY, load text, created timestamptz DEFAULT now(), result jsonb, sent boolean DEFAULT false);
"""

def conn():
    return psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row, autocommit=True)

def init():
    with conn() as c: c.execute(SCHEMA)
