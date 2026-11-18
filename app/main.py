import os, csv, io, json, datetime as dt, httpx
from pathlib import Path
from fastapi import FastAPI, UploadFile, HTTPException, Body
from fastapi.responses import HTMLResponse
import db, planner, telegram, airtable, dispatch

app = FastAPI(title="LogTru demo")

@app.on_event("startup")
def _s(): db.init()

@app.get("/api/health")
def health(): return {"ok": True}

@app.post("/api/loads")
def add_load(l: dict):
    with db.conn() as c:
        c.execute("INSERT INTO loads(load,origin,destination,pickup,delivery,unit,rate) VALUES (%(load)s,%(origin)s,%(destination)s,%(pickup)s,%(delivery)s,%(unit)s,%(rate)s) ON CONFLICT (load) DO UPDATE SET origin=EXCLUDED.origin, destination=EXCLUDED.destination", {**dict(pickup=None, delivery=None, unit=None, rate=None), **l})
    return {"ok": True}

@app.post("/api/import/fills")
async def import_fills(file: UploadFile):
    """Pipe file: sid|name|city|st|lat|lng|time|paid  (fleet-paid prices from United Fuel)."""
    n = 0
    with db.conn() as c:
        for line in (await file.read()).decode().splitlines():
            p = line.split("|")
            if len(p) < 8: continue
            c.execute("INSERT INTO stations VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING", (p[0], p[1], p[2], p[3], float(p[4]), float(p[5])))
            c.execute("INSERT INTO prices VALUES (%s,%s,%s) ON CONFLICT DO NOTHING", (p[0], p[6], float(p[7]))); n += 1
    return {"imported": n}

@app.post("/api/import/uf")
def import_uf(rows: list[dict] = Body(...)):
    """Rows from the United Fuel robot: name, price (discounted), retail, updated (MM/DD/YYYY), st, city, address.
    New stations are geocoded with HERE; known ones keep their coordinates. Price = discounted price."""
    key = os.environ.get("HERE_API_KEY")
    if not key: raise HTTPException(400, "HERE_API_KEY not set (needed to geocode station addresses)")
    n = geo = skipped = wrong = 0
    with db.conn() as c:
        for r in rows:
            try:
                price = float(r["price"]); sid = "UF:" + r["name"].strip(); st = r["st"].strip().upper()
                seen = dt.datetime.strptime(r["updated"], "%m/%d/%Y").date().isoformat()
                if not 1 < price < 15: raise ValueError("price out of range")      # e.g. $0.00 listings
            except Exception:
                skipped += 1; continue
            # (re)geocode unless we already hold coordinates verified to be in the station's own state
            if not c.execute("SELECT 1 FROM stations WHERE sid=%s AND lat IS NOT NULL AND geo_state=%s", (sid, st)).fetchone():
                try:
                    lat, lng, gs = planner._geocode_full(f"{r['address']}, {r['city']}, {st}", key)
                except Exception:
                    skipped += 1; continue
                geo += 1
                if gs != st:                                   # HERE matched a place in another state: do not trust it
                    wrong += 1
                    c.execute("UPDATE stations SET lat=NULL, lng=NULL WHERE sid=%s", (sid,)); continue
                c.execute("""INSERT INTO stations(sid,name,city,st,lat,lng,source,geo_state) VALUES (%s,%s,%s,%s,%s,%s,'uf',%s)
                             ON CONFLICT (sid) DO UPDATE SET lat=EXCLUDED.lat, lng=EXCLUDED.lng, source='uf', geo_state=EXCLUDED.geo_state""",
                          (sid, r["name"], r["city"], st, lat, lng, gs))
            c.execute("""INSERT INTO prices VALUES (%s,%s,%s) ON CONFLICT (sid, seen) DO UPDATE SET price=EXCLUDED.price""", (sid, seen, price))
            n += 1
    return {"stored": n, "geocoded": geo, "wrong_state": wrong, "skipped": skipped}

@app.post("/api/sync/airtable")
def sync_airtable():
    try: return airtable.sync()
    except Exception as e: raise HTTPException(400, str(e))

@app.get("/api/loads")
def loads():
    with db.conn() as c:
        return c.execute("""SELECT l.*, p.result AS plan, p.created AS plan_at FROM loads l
                            LEFT JOIN LATERAL (SELECT result, created FROM plans WHERE load = l.load ORDER BY created DESC LIMIT 1) p ON true
                            ORDER BY l.load DESC""").fetchall()

@app.get("/api/trucks")
def trucks():
    with db.conn() as c:
        return c.execute("""SELECT t.*, (SELECT count(*) FROM loads l WHERE l.truck = t.unit) AS loads
                            FROM trucks t ORDER BY t.unit""").fetchall()

@app.post("/api/trucks/import")
def import_trucks(rows: list[dict] = Body(...)):
    """[{unit, driver, city?, st?}]. Location is only changed when city and st are given."""
    n = placed = 0
    with db.conn() as c:
        for r in rows:
            unit = str(r.get("unit", "")).strip()
            if not unit: continue
            c.execute("""INSERT INTO trucks(unit, driver) VALUES (%s,%s)
                         ON CONFLICT (unit) DO UPDATE SET driver = coalesce(nullif(EXCLUDED.driver,''), trucks.driver)""",
                      (unit, (r.get("driver") or "").strip())); n += 1
            city, st = (r.get("city") or "").strip(), (r.get("st") or "").strip().upper()
            if city and st:
                g = dispatch.geocode(c, f"{city}, {st}")
                if g:
                    c.execute("UPDATE trucks SET city=%s, st=%s, lat=%s, lng=%s WHERE unit=%s", (city, st, g[0], g[1], unit)); placed += 1
                else:
                    c.execute("UPDATE trucks SET city=%s, st=%s WHERE unit=%s", (city, st, unit))
    return {"trucks": n, "located": placed}

@app.post("/api/fuel/import")
def import_fuel(rows: list[dict] = Body(...)):
    """QuickManage fuel purchases. Re-sending the same purchase never duplicates it."""
    import hashlib
    new = 0
    with db.conn() as c:
        for r in rows:
            try:
                key = hashlib.md5(f"{r['tdate']}|{r['txn']}|{r['equip']}|{r['gallons']}|{r['diesel_amt']}".encode()).hexdigest()
                cur = c.execute("""INSERT INTO fuel_txns(key,tdate,txn,equip,driver,merchant,city,st,gallons,ppg,diesel_amt,def_amt,fee,total,discount,paid)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (key) DO UPDATE SET driver=EXCLUDED.driver, discount=EXCLUDED.discount, paid=EXCLUDED.paid""",
                    (key, r["tdate"], r["txn"], r["equip"], r.get("driver"), r.get("merchant"), r.get("city"), r.get("st"), r["gallons"], r["ppg"],
                     r.get("diesel_amt"), r.get("def_amt"), r.get("fee"), r.get("total"), r.get("discount"), r.get("paid")))
                new += 1
            except KeyError:
                continue
        total = c.execute("SELECT count(*) AS n FROM fuel_txns").fetchone()["n"]
    return {"received": new, "total_in_database": total}

@app.get("/api/fuel")
def list_fuel(equip: str | None = None, since: str | None = None):
    q, a = "SELECT * FROM fuel_txns WHERE gallons >= 5", []
    if equip: q += " AND equip=%s"; a.append(equip)
    if since: q += " AND tdate >= %s"; a.append(since)
    with db.conn() as c:
        return c.execute(q + " ORDER BY tdate DESC, equip", a).fetchall()

@app.delete("/api/trucks/{unit}")
def delete_truck(unit: str):
    with db.conn() as c:
        c.execute("UPDATE loads SET truck=NULL, assign_info=NULL WHERE truck=%s", (unit,))
        c.execute("DELETE FROM trucks WHERE unit=%s", (unit,))
    return {"ok": True}

@app.post("/api/assign/run")
def assign_run():
    with db.conn() as c: return dispatch.run(c)

@app.post("/api/assign/clear")
def assign_clear():
    with db.conn() as c: c.execute("UPDATE loads SET truck=NULL, assign_info=NULL")
    return {"ok": True}

@app.post("/api/loads/{load}/truck")
def set_truck(load: str, body: dict = Body(...)):
    unit = (body.get("unit") or "").strip() or None
    with db.conn() as c:
        if unit and not c.execute("SELECT 1 FROM trucks WHERE unit=%s", (unit,)).fetchone(): raise HTTPException(404, "truck not found")
        c.execute("UPDATE loads SET truck=%s, assign_info=%s WHERE load=%s", (unit, json.dumps({"manual": True}) if unit else None, load))
    return {"ok": True}

def _stations():
    with db.conn() as c:
        return c.execute("SELECT sid, name, city, st, lat, lng, price FROM current_stations").fetchall()

@app.post("/api/plan/{load}")
def make_plan(load: str, send: bool = False):
    with db.conn() as c:
        l = c.execute("SELECT * FROM loads WHERE load=%s", (load,)).fetchone()
    if not l: raise HTTPException(404, "load not found")
    key = os.environ.get("GOOGLE_MAPS_KEY")
    if not key and not os.environ.get("HERE_API_KEY"): raise HTTPException(400, "Set HERE_API_KEY (or GOOGLE_MAPS_KEY) in .env")
    try:
        res = planner.plan(l["origin"], l["destination"], _stations(), key)
    except httpx.HTTPStatusError as e:
        raise HTTPException(502, f"Routing API said {e.response.status_code}: {e.response.text[:300]}")
    except Exception as e:
        raise HTTPException(500, f"Planner error: {e}")
    msg = telegram.format_plan(load, l["origin"], l["destination"], res)
    out = dict(plan=res, message=msg)
    if send: out["telegram"] = telegram.send(msg)
    with db.conn() as c:
        c.execute("INSERT INTO plans(load,result,sent) VALUES (%s,%s,%s)", (load, json.dumps(res), send))
    return out

@app.get("/api/status")
def status():
    with db.conn() as c:
        s = c.execute("SELECT count(*) AS n, max(seen) AS newest FROM current_stations").fetchone()
        l = c.execute("SELECT count(*) AS n FROM loads").fetchone()
    return dict(loads=l["n"], stations=s["n"], newest=s["newest"].date().isoformat() if s["newest"] else None)

@app.get("/", response_class=HTMLResponse)
def home():
    return (Path(__file__).parent / "dashboard.html").read_text()
