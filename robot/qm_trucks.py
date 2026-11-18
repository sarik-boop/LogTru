"""QuickManage trucks -> app: reads Fleet > Equipment > Trucks (truck number and driver) and sends it to /api/trucks/import.
Only the first page of the list is read. Location is not in QuickManage; set it in the app (Samsara will fill it later).
Run: docker compose run --rm robot python3 qm_trucks.py"""
import os, re, httpx
from playwright.sync_api import sync_playwright
import common
import quickmanage

URL = "https://app.quickmanage.com/account-settings/equipments/trucks"
CARRIER = "Calzada Family Transport LLC"
OWNERSHIP = ("Company", "Owner Operator’s", "Owner Operator's")

def parse(text):
    L = [x.strip() for x in text.splitlines() if x.strip()]
    starts = [i for i in range(len(L) - 1) if L[i] not in ("New", "IFTA") and (L[i + 1].startswith("VIN :") or (i + 2 < len(L) and L[i + 1] in ("New", "IFTA") and L[i + 2].startswith("VIN :")))]
    out = []
    for n, i in enumerate(starts):
        end = starts[n + 1] if n + 1 < len(starts) else len(L)
        seg = L[i:end]
        drivers = []
        if CARRIER in seg:
            for x in seg[seg.index(CARRIER) + 1:]:
                if x in OWNERSHIP: break
                drivers.append(x.lstrip(", ").strip())
        out.append(dict(unit=L[i], driver=" / ".join(d for d in drivers if d)))
    return out

def main():
    common.gate("qm", hours=os.environ.get("QM_HOURS", "6-22"))
    with sync_playwright() as p:
        b, pg = common.open_session(p, "qm", URL, r"app\.quickmanage\.com/account-settings", quickmanage.login)
        pg.wait_for_selector("text=Truck #", timeout=60000); pg.wait_for_timeout(3000)
        rows = parse(pg.inner_text("body")); b.close()
    print(f"read {len(rows)} trucks", flush=True)
    r = httpx.post(os.environ.get("APP_URL", "http://app:8000") + "/api/trucks/import", json=rows, timeout=120)
    r.raise_for_status(); print(r.json())

if __name__ == "__main__":
    main()
