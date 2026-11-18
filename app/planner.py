"""Fuel planner: cheapest fuel stops along a route (DP over stations on the corridor).
Logic taken from the validated analysis (6.5 MPG, 200 gal tank, 30 gal reserve)."""
import math, os, httpx

MPG, TANK, RESERVE, START, MINFILL, STEP, CORRIDOR_MI = 6.5, 200, 30, 110, 50, 5, 5.0

def hav(a, b):
    R = 3958.8
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2-la1)/2)**2 + math.cos(la1)*math.cos(la2)*math.sin((lo2-lo1)/2)**2
    return 2*R*math.asin(math.sqrt(h))

def decode(p):
    pts, i, lat, lng = [], 0, 0, 0
    while i < len(p):
        for k in (0, 1):
            r = s = 0
            while True:
                b = ord(p[i]) - 63; i += 1
                r |= (b & 0x1f) << s; s += 5
                if b < 0x20: break
            d = ~(r >> 1) if r & 1 else r >> 1
            if k == 0: lat += d
            else: lng += d
        pts.append((lat/1e5, lng/1e5))
    return pts


_T = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
_V = {c: i for i, c in enumerate(_T)}

def decode_flex(p):
    """HERE flexible polyline -> [(lat, lng)]"""
    vals, i = [], 0
    while i < len(p):
        r = s = 0
        while True:
            b = _V[p[i]]; i += 1
            r |= (b & 0x1f) << s; s += 5
            if not b & 0x20: break
        vals.append(r)
    hdr = vals[1]
    prec = hdr & 15; third = (hdr >> 4) & 7
    f = 10 ** prec; n = 3 if third else 2
    pts, cur = [], [0, 0, 0]
    body = vals[2:]
    for j in range(0, len(body) - n + 1, n):
        for k in range(n):
            v = body[j + k]
            cur[k] += ~(v >> 1) if v & 1 else v >> 1
        pts.append((cur[0] / f, cur[1] / f))
    return pts

# Truck profile (override in .env). Defaults: 5-axle tractor-trailer, 13.6 ft x 8.5 ft, 80,000 lb.
def _truck():
    g = lambda k, d: os.environ.get(k, d)
    return {"vehicle[type]": "tractor", "vehicle[trailerCount]": g("TRUCK_TRAILERS", "1"),
            "vehicle[height]": g("TRUCK_HEIGHT_CM", "415"), "vehicle[width]": g("TRUCK_WIDTH_CM", "259"),
            "vehicle[length]": g("TRUCK_LENGTH_CM", "2200"), "vehicle[grossWeight]": g("TRUCK_WEIGHT_KG", "36287"),
            "vehicle[axleCount]": g("TRUCK_AXLES", "5")}

def _geocode(q, key):
    r = httpx.get("https://geocode.search.hereapi.com/v1/geocode", params={"q": q, "in": "countryCode:USA", "limit": 1, "apiKey": key}, timeout=30)
    r.raise_for_status()
    it = r.json().get("items") or []
    if not it: raise ValueError(f"HERE could not find address: {q}")
    p = it[0]["position"]
    return f"{p['lat']},{p['lng']}"

def route_here(origin, dest, key):
    prm = {"transportMode": "truck", "origin": _geocode(origin, key), "destination": _geocode(dest, key),
           "return": "polyline,summary", "apiKey": key, **_truck()}
    r = httpx.get("https://router.hereapi.com/v8/routes", params=prm, timeout=60)
    r.raise_for_status()
    secs = r.json()["routes"][0]["sections"]
    pts = []
    for sec in secs: pts += decode_flex(sec["polyline"])
    return dict(pts=pts, meters=sum(x["summary"]["length"] for x in secs), seconds=sum(x["summary"]["duration"] for x in secs))

def route(origin, dest, key):
    r = httpx.post("https://routes.googleapis.com/directions/v2:computeRoutes", timeout=60,
        headers={"X-Goog-Api-Key": key, "X-Goog-FieldMask": "routes.distanceMeters,routes.staticDuration,routes.polyline.encodedPolyline"},
        json=dict(origin={"address": origin}, destination={"address": dest}, travelMode="DRIVE",
                  routingPreference="TRAFFIC_UNAWARE", units="IMPERIAL"))
    r.raise_for_status()
    return r.json()["routes"][0]

def stations_on(pts, stations):
    cm = [0.0]
    for a, b in zip(pts, pts[1:]): cm.append(cm[-1] + hav(a, b))
    idx = list(range(0, len(pts), max(1, len(pts)//4000))) + [len(pts)-1]
    out = []
    for s in stations:
        best = min(((hav((s["lat"], s["lng"]), pts[i]), i) for i in idx))
        if best[0] <= CORRIDOR_MI:
            out.append(dict(s, mile=cm[best[1]], price=s["price"]))
    return sorted(out, key=lambda r: r["mile"]), cm[-1]

def dp_fuel(total_mi, sts, start=START):
    pts = sts + [dict(mile=total_mi, end=True)]
    cost = {float(start): (0.0, 0, [])}
    prev = 0
    for s in pts:
        need = (s["mile"] - prev) / MPG; prev = s["mile"]
        arr = {}
        for g, v in cost.items():
            g2 = round(g - need, 1)
            if g2 < RESERVE - 1e-9: continue
            if g2 not in arr or v[0] < arr[g2][0]: arr[g2] = v
        if s.get("end"):
            ok = [(v[0], v, g) for g, v in arr.items() if g >= start - 0.05]
            if not ok: return None
            c, v, g = min(ok, key=lambda x: x[0])
            return dict(cost=round(c, 2), plan=v[2], gallons=round(total_mi/MPG, 1))
        nxt = dict(arr)
        for g, v in arr.items():
            for buy in range(MINFILL, int(TANK - g) + 1, STEP):
                g3 = round(g + buy, 1); c = v[0] + buy*s["price"]
                if g3 not in nxt or c < nxt[g3][0]:
                    nxt[g3] = (c, v[1]+1, v[2] + [dict(station=s["name"], city=s["city"], st=s["st"], gallons=buy, price=s["price"], mile=round(s["mile"]))])
        cost = nxt
    return None

def plan(origin, dest, stations, key, start=START):
    if os.environ.get("HERE_API_KEY"):
        r = route_here(origin, dest, os.environ["HERE_API_KEY"]); pts, meters, secs = r["pts"], r["meters"], r["seconds"]; src = "HERE truck"
    else:
        g = route(origin, dest, key)
        pts, meters, secs, src = decode(g["polyline"]["encodedPolyline"]), g["distanceMeters"], int(g["staticDuration"].rstrip("s")), "Google car (no truck rules)"
    sts, poly_mi = stations_on(pts, stations)
    miles = meters / 1609.344
    scale = miles / poly_mi
    for s in sts: s["mile"] *= scale
    res = dp_fuel(miles, sts, start)
    return dict(miles=round(miles, 1), hours=round(secs/3600, 2), router=src, stations_on_route=len(sts), fuel=res)
