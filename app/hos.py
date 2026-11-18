"""Trip clock for one solo driver under US hours-of-service rules (property-carrying, simplified):
11 h driving and a 14 h on-duty window per shift, a 30 min break after 8 h driving, then 10 h off duty (the 'sleep').
Fuel stops take FUEL_MIN minutes, count as on-duty time and as the 30 min break. A planning estimate, not a legal log."""
import os

FUEL_MIN = float(os.environ.get("FUEL_STOP_MIN", "30"))
DRIVE_MAX, WINDOW, BREAK_AFTER, REST_H = 11.0, 14.0, 8.0, 10.0
if os.environ.get("HOS_RULES", "0") != "1":  # default: pure driving time plus fuel stops, no breaks or sleep
    DRIVE_MAX = WINDOW = BREAK_AFTER = 1e9
EPS = 1e-9

def schedule(miles, drive_h, stops, parking=()):
    """stops: fuel stops [{mile, station, city, st, gallons, price}] in route order.
    parking: priced stations near the route [{mile, name, city, st}], used to name a place to sleep."""
    mph = miles / drive_h if drive_h else 55.0
    t = pos = shift_drive = shift_start = since_break = 0.0
    ev, fuel_h = [], 0.0
    marks = [(s["mile"], s) for s in stops] + [(miles, None)]
    for mile, s in marks:
        remaining = max(0.0, (mile - pos) / mph)
        while remaining > EPS:
            room = min(DRIVE_MAX - shift_drive, WINDOW - (t - shift_start), BREAK_AFTER - since_break)
            if room <= EPS:
                if BREAK_AFTER - since_break <= EPS and DRIVE_MAX - shift_drive > EPS and WINDOW - (t - shift_start) > EPS:
                    ev.append(dict(kind="break", mile=round(pos), at=round(t, 2), hours=0.5))
                    t += 0.5; since_break = 0.0
                else:
                    near = None
                    back = [p for p in parking if pos - 80 <= p["mile"] <= pos]
                    if back:
                        p = max(back, key=lambda x: x["mile"]); near = dict(station=p["name"], city=p["city"], st=p["st"], mile=round(p["mile"]))
                    ev.append(dict(kind="rest", mile=round(pos), at=round(t, 2), hours=REST_H, near=near))
                    t += REST_H; shift_drive = 0.0; shift_start = t; since_break = 0.0
                continue
            d = min(remaining, room)
            t += d; shift_drive += d; since_break += d; pos += d * mph; remaining -= d
        pos = mile
        if s:
            ev.append(dict(kind="fuel", mile=round(mile), at=round(t, 2), hours=round(FUEL_MIN / 60, 2), station=s["station"], city=s["city"],
                           st=s["st"], gallons=s["gallons"], price=s["price"]))
            t += FUEL_MIN / 60; fuel_h += FUEL_MIN / 60; since_break = 0.0
    rest_h = sum(e["hours"] for e in ev if e["kind"] == "rest")
    break_h = sum(e["hours"] for e in ev if e["kind"] == "break")
    return dict(total_h=round(t, 2), drive_h=round(drive_h, 2), fuel_h=round(fuel_h, 2), rest_h=round(rest_h, 1), break_h=round(break_h, 1),
                sleeps=sum(1 for e in ev if e["kind"] == "rest"), events=ev)
