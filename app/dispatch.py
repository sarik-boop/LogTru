"""Truck assignment. Rule: take loads in pickup-time order; give each to the truck that can reach the pickup in time
with the least empty (deadhead) miles. After a load, the truck is treated as free at the drop-off city at delivery time.
Distances are straight-line x1.25 (road factor), speed 50 mph, no hours-of-service rules: it is a planning estimate."""
import re, os, datetime as dt
import planner

TZ = {"EST": -5, "EDT": -4, "CST": -6, "CDT": -5, "MST": -7, "MDT": -6, "PST": -8, "PDT": -7}
PAT = re.compile(r"(\d\d)/(\d\d)/(\d{4}) (\d\d):(\d\d) ([A-Z]{3})")
ROAD, MPH = 1.25, 50.0
H = lambda x: dt.timedelta(hours=x)

def parse_dt(s):
    m = PAT.search(s or "")
    if not m: return None
    mo, d, y, hh, mm, tz = m.groups()
    return dt.datetime(int(y), int(mo), int(d), int(hh), int(mm), tzinfo=dt.timezone(H(TZ.get(tz, -6))))

def geocode(c, q):
    """City or address -> (lat, lng), cached in the geo table."""
    if not q: return None
    r = c.execute("SELECT lat, lng FROM geo WHERE q=%s", (q,)).fetchone()
    if r: return r["lat"], r["lng"]
    key = os.environ.get("HERE_API_KEY")
    if not key: return None
    try: lat, lng, _ = planner._geocode_full(q, key)
    except Exception: return None
    c.execute("INSERT INTO geo VALUES (%s,%s,%s) ON CONFLICT DO NOTHING", (q, lat, lng))
    return lat, lng

def _delivery(l, pu):
    return parse_dt(l.get("delivery")) or pu + H((l.get("loaded_mi") or 0) / MPH)

def run(c, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    trucks = c.execute("SELECT * FROM trucks WHERE lat IS NOT NULL ORDER BY unit").fetchall()
    no_loc = c.execute("SELECT count(*) AS n FROM trucks WHERE lat IS NULL").fetchone()["n"]
    state = {t["unit"]: dict(lat=t["lat"], lng=t["lng"], free=max(t["free_at"] or now, now)) for t in trucks}
    loads = c.execute("SELECT * FROM loads WHERE coalesce(status,'') NOT IN ('In Transit','Completed','Cancelled')").fetchall()
    far = now + dt.timedelta(days=60)
    loads.sort(key=lambda l: parse_dt(l["pickup"]) or far)
    for l in loads:                                   # trucks already on a load are busy until its drop-off
        if l["truck"] in state:
            pu, dest = parse_dt(l["pickup"]), geocode(c, l["destination"])
            if pu and dest:
                state[l["truck"]] = dict(lat=dest[0], lng=dest[1], free=max(_delivery(l, pu), now))
    done, left = 0, []
    for l in loads:
        if l["truck"]: continue
        pu, o, d = parse_dt(l["pickup"]), geocode(c, l["origin"]), geocode(c, l["destination"])
        if not pu or not o:
            left.append(dict(load=l["load"], reason="Pickup time or origin not understood")); continue
        if not state:
            left.append(dict(load=l["load"], reason="No truck has a known location")); continue
        best = None
        for u, s in state.items():
            dh = planner.hav((s["lat"], s["lng"]), o) * ROAD
            eta = s["free"] + H(dh / MPH)
            slack = (pu - eta).total_seconds() / 3600
            k = (slack < 0, dh)                       # on time first, then fewest empty miles
            if best is None or k < best[0]: best = (k, u, dh, eta, slack)
        _, u, dh, eta, slack = best
        if slack < 0:
            left.append(dict(load=l["load"], reason=f"Closest truck {u} would arrive {abs(slack):.0f} h late")); continue
        c.execute("UPDATE loads SET truck=%s, assign_info=%s WHERE load=%s",
                  (u, __import__("json").dumps(dict(deadhead_mi=round(dh), eta=eta.isoformat(), slack_h=round(slack, 1), auto=True)), l["load"]))
        dest = d or o
        state[u] = dict(lat=dest[0], lng=dest[1], free=_delivery(l, pu))
        done += 1
    return dict(assigned=done, unassigned=left, trucks_without_location=no_loc)
