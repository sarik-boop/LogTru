"""Airtable -> Postgres sync. Airtable is the editable source; Postgres is the app's working copy."""
import os, httpx
import db

BASE = "app8zoPghGYT4p0CZ"
T_LOADS, T_STATIONS = "tbl0xTquarjpevIHD", "tblPcZ2IpffQtpe30"

def _rows(table):
    tok = os.environ.get("AIRTABLE_TOKEN")
    if not tok:
        raise RuntimeError("AIRTABLE_TOKEN not set in .env")
    out, offset = [], None
    while True:
        r = httpx.get(f"https://api.airtable.com/v0/{BASE}/{table}", timeout=60,
                      headers={"Authorization": f"Bearer {tok}"},
                      params={"pageSize": 100, **({"offset": offset} if offset else {})})
        r.raise_for_status()
        j = r.json()
        out += j["records"]
        offset = j.get("offset")
        if not offset: return out

def sync():
    n_loads = n_st = 0
    with db.conn() as c:
        for rec in _rows(T_LOADS):
            f = rec["fields"]
            if not f.get("QM Trip #"): continue
            c.execute("""INSERT INTO loads(load,origin,destination,pickup,delivery,unit,rate,source,broker,broker_load,status,
                                           origin_facility,dest_facility,deadhead_mi,loaded_mi,weight_lbs)
                         VALUES (%s,%s,%s,%s,%s,%s,%s,'airtable',%s,%s,%s,%s,%s,%s,%s,%s)
                         ON CONFLICT (load) DO UPDATE SET origin=EXCLUDED.origin, destination=EXCLUDED.destination,
                         pickup=EXCLUDED.pickup, delivery=EXCLUDED.delivery, rate=EXCLUDED.rate, broker=EXCLUDED.broker,
                         broker_load=EXCLUDED.broker_load, status=EXCLUDED.status, origin_facility=EXCLUDED.origin_facility,
                         dest_facility=EXCLUDED.dest_facility, deadhead_mi=EXCLUDED.deadhead_mi, loaded_mi=EXCLUDED.loaded_mi,
                         weight_lbs=EXCLUDED.weight_lbs""",
                      (f["QM Trip #"], f.get("Origin"), f.get("Destination"), f.get("Pickup (local)"),
                       f.get("Delivery (local)"), None, f.get("Rate"), f.get("Broker"), f.get("Broker Load #"), f.get("Status"),
                       f.get("Origin Facility"), f.get("Destination Facility"), f.get("Deadhead mi"), f.get("Loaded mi"),
                       f.get("Weight lbs"))); n_loads += 1
        for rec in _rows(T_STATIONS):
            f = rec["fields"]
            if f.get("Latitude") is None or f.get("Retail $/gal") is None: continue
            price = f["Retail $/gal"] - (f.get("Discount $/gal") or 0)   # price paid after United Fuel discount
            sid = rec["id"]
            c.execute("INSERT INTO stations VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (sid) DO UPDATE SET name=EXCLUDED.name",
                      (sid, f.get("Station"), f.get("City"), f.get("State"), f["Latitude"], f["Longitude"]))
            c.execute("INSERT INTO prices VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
                      (sid, f.get("Price Date") or "2026-11-01", price)); n_st += 1
    return {"loads": n_loads, "stations": n_st}
