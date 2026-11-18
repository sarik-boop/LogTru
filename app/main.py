import os, csv, io, json, datetime as dt, httpx
from fastapi import FastAPI, UploadFile, HTTPException
from fastapi.responses import HTMLResponse
import db, planner, telegram, airtable

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

@app.post("/api/sync/airtable")
def sync_airtable():
    try: return airtable.sync()
    except Exception as e: raise HTTPException(400, str(e))

@app.get("/api/loads")
def loads():
    with db.conn() as c: return c.execute("SELECT * FROM loads ORDER BY load DESC").fetchall()

def _stations():
    with db.conn() as c:
        return c.execute("""SELECT DISTINCT ON (s.sid) s.sid, s.name, s.city, s.st, s.lat, s.lng, p.price
                            FROM stations s JOIN prices p USING (sid) ORDER BY s.sid, p.seen DESC""").fetchall()

@app.post("/api/plan/{load}")
def make_plan(load: str, send: bool = False):
    with db.conn() as c:
        l = c.execute("SELECT * FROM loads WHERE load=%s", (load,)).fetchone()
    if not l: raise HTTPException(404, "load not found")
    key = os.environ.get("GOOGLE_MAPS_KEY")
    if not key: raise HTTPException(400, "GOOGLE_MAPS_KEY not set")
    try:
        res = planner.plan(l["origin"], l["destination"], _stations(), key)
    except httpx.HTTPStatusError as e:
        raise HTTPException(502, f"Google Routes API said {e.response.status_code}: {e.response.text[:300]}")
    except Exception as e:
        raise HTTPException(500, f"Planner error: {e}")
    msg = telegram.format_plan(load, l["origin"], l["destination"], res)
    out = dict(plan=res, message=msg)
    if send: out["telegram"] = telegram.send(msg)
    with db.conn() as c:
        c.execute("INSERT INTO plans(load,result,sent) VALUES (%s,%s,%s)", (load, json.dumps(res), send))
    return out

@app.get("/", response_class=HTMLResponse)
def home():
    return """<!doctype html><meta charset=utf-8><title>LogTru</title>
<style>body{font:15px system-ui;margin:2rem auto;max-width:900px;padding:0 1rem}table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid #ddd;padding:6px;text-align:left}button{padding:4px 10px}pre{background:#f5f5f5;padding:10px;white-space:pre-wrap}</style>
<h1>LogTru: load to fuel plan</h1><p><button onclick="sync()">Sync from Airtable</button> <span id=m></span></p><table id=t><tr><th>Load<th>Route<th>Truck<th></table><pre id=o>Pick a load and press Plan.</pre>
<script>
async function go(){const r=await (await fetch('/api/loads')).json();const t=document.getElementById('t');
for(const l of r){const tr=t.insertRow();tr.innerHTML=`<td>${l.load}<td>${l.origin} to ${l.destination}<td>${l.unit||''}<td><button onclick="plan('${l.load}',false)">Plan</button> <button onclick="plan('${l.load}',true)">Plan + Telegram</button>`}}
async function plan(id,send){o.textContent='Planning...';const r=await fetch('/api/plan/'+id+'?send='+send,{method:'POST'});let j={};try{j=await r.json()}catch(e){};o.textContent=j.message||j.detail||('Error '+r.status)}
async function sync(){m.textContent='Syncing...';const r=await fetch('/api/sync/airtable',{method:'POST'});const j=await r.json();m.textContent=r.ok?('Loaded '+j.loads+' loads, '+j.stations+' stations. Reload the page.'):('Error: '+(j.detail||''))}
go()</script>"""
