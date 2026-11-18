"""QuickManage fuel purchases -> app database (table fuel_txns). Not Airtable.
Reads Accounting > Fuel & Tolls > Fuel Transactions (newest first), a few pages, and sends them to /api/fuel/import.
Run: docker compose run --rm robot python3 qm_fuel.py"""
import os, re, datetime as dt, httpx
from playwright.sync_api import sync_playwright
import common
import quickmanage

BASE = "https://app.quickmanage.com/accounts/fuel-toll/fuel-transactions/list?page={p}&year={y}&search_term=&sort_by=&settled={s}"
PAGES = int(os.environ.get("QM_FUEL_PAGES", "3"))
DATE = re.compile(r"^\d\d/\d\d/\d{4}$")
MONEY = lambda s: None if s in ("-", "") else float(s.replace("$", "").replace(",", ""))

def parse(text):
    L = [x.strip() for x in text.splitlines() if x.strip()]
    drivers = {}
    for x in L:                                              # trailing "1014Yeabsira Kebede" lines
        m = re.match(r"^(\d{3,7})([A-Z][A-Za-z'.\- ]+)$", x)
        if m: drivers[m.group(1)] = m.group(2).strip()
    out = []
    for i, x in enumerate(L):
        if not DATE.match(x) or i + 15 > len(L): continue
        r = L[i:i + 15]
        m = re.match(r"^([\d.,]+) / \$([\d.,]+)$", r[7])
        if not m or not r[3].isdigit() and not r[3].isalnum(): continue
        mm, dd, yy = r[0].split("/")
        loc = r[5]; st = loc[-4:-2] if loc.endswith("US") else ""
        city = (loc[:-4] if loc.endswith("US") else loc).strip().rstrip(",")
        out.append(dict(tdate=f"{yy}-{mm}-{dd}", txn=r[2], equip=r[3], driver=drivers.get(r[3], ""), merchant=r[4], city=city, st=st,
                        diesel_amt=MONEY(r[6]), gallons=float(m.group(1).replace(",", "")), ppg=float(m.group(2).replace(",", "")),
                        def_amt=MONEY(r[9]), fee=MONEY(r[10]), total=MONEY(r[11]), discount=MONEY(r[12]), paid=MONEY(r[13])))
    return out

def main():
    common.gate("qm", hours=os.environ.get("QM_HOURS", "6-22"))
    rows, y = [], dt.date.today().year
    with sync_playwright() as p:
        b, pg = common.open_session(p, "qm", BASE.format(p=0, y=y, s="false"), r"app\.quickmanage\.com/accounts", quickmanage.login)
        for n in range(PAGES):
            if n: pg.goto(BASE.format(p=n, y=y, s="false")); common.pause(2, 4)
            try: pg.wait_for_selector("text=Merchant/Location", timeout=60000)
            except Exception: break
            pg.wait_for_timeout(4000)
            got = parse(pg.inner_text("body")); rows += got
            print(f"page {n}: {len(got)} purchases", flush=True)
            if len(got) < 20: break
        b.close()
    if not rows: print("nothing read"); return
    r = httpx.post(os.environ.get("APP_URL", "http://app:8000") + "/api/fuel/import", json=rows, timeout=120)
    r.raise_for_status(); print(r.json())

if __name__ == "__main__":
    main()
