"""QuickManage robot (UNTESTED against the live login page): logs in, reads the Trips list, upserts into Airtable 'Active Loads'.
Credentials come from .env (QM_USER, QM_PASS). Run: docker compose run --rm robot"""
import os, re, sys, datetime as dt, httpx
from playwright.sync_api import sync_playwright

BASE, TABLE = "app8zoPghGYT4p0CZ", "tbl0xTquarjpevIHD"
URL = "https://app.quickmanage.com"
STATUS = {"Dispatched", "In Transit", "Upcoming"}
DT = re.compile(r"^\d\d/\d\d/\d{4} \d\d:\d\d [A-Z]{3}$")
num = lambda s: float(re.sub(r"[^\d.]", "", s) or 0)

def parse(text):
    L = [x.strip() for x in text.splitlines() if x.strip()]
    trips = []
    for i, x in enumerate(L):                       # trip numbers appear after each "FTL"
        if x in ("FTL", "LTL") and i + 1 < len(L) and re.fullmatch(r"\d{4,6}", L[i + 1]): trips.append(L[i + 1])
    out, k = [], 0
    for i, x in enumerate(L):
        if x not in STATUS or i + 2 >= len(L) or k >= len(trips): continue
        j = i + 1
        rec = {"QM Trip #": trips[k], "Status": x, "Broker Load #": L[j], "Broker": L[j + 1]}; k += 1
        j += 2
        if not L[j].isdigit(): j += 1                # relative time ("In 16 Hours")
        j += 1                                       # stop number "1"
        rec["Origin"], rec["Origin Facility"] = L[j], L[j + 1]; j += 2
        if L[j] == "R": j += 1
        rec["Pickup (local)"] = L[j]; j += 1
        j += 1                                       # stop number "2"
        rec["Destination"], rec["Destination Facility"] = L[j], L[j + 1]; j += 2
        if L[j] == "R": j += 1
        rec["Delivery (local)"] = L[j]; j += 1
        tail = L[j:j + 25]
        mi = [num(t) for t in tail if t.endswith(" mi")]
        if len(mi) >= 2: rec["Deadhead mi"], rec["Loaded mi"] = mi[0], mi[1]
        m = next((t for t in tail if t.startswith("$") and "/mi" not in t and "Accs" not in t), None)
        if m: rec["Rate"] = num(m)
        out.append(rec)
    return out

def upsert(records):
    tok = os.environ["AIRTABLE_WRITE_TOKEN"]        # needs data.records:write
    for i in range(0, len(records), 10):
        r = httpx.patch(f"https://api.airtable.com/v0/{BASE}/{TABLE}", timeout=60, headers={"Authorization": f"Bearer {tok}"},
            json={"performUpsert": {"fieldsToMergeOn": ["QM Trip #"]}, "typecast": True,
                  "records": [{"fields": {**f, "Pulled": dt.date.today().isoformat()}} for f in records[i:i + 10]]})
        r.raise_for_status()

def main():
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page()
        pg.goto(URL + "/login")
        pg.get_by_placeholder(re.compile("email|user", re.I)).first.fill(os.environ["QM_USER"])
        pg.locator("input[type=password]").first.fill(os.environ["QM_PASS"])
        pg.keyboard.press("Enter")
        pg.wait_for_url(re.compile("dashboard|dispatching"), timeout=60000)
        pg.get_by_role("link", name="Loads & Trips").click()
        pg.wait_for_selector("text=Active Loads", timeout=60000); pg.wait_for_timeout(4000)
        recs = parse(pg.inner_text("body"))
        print(f"parsed {len(recs)} loads")
        if recs: upsert(recs)
        b.close()

if __name__ == "__main__":
    main()
