"""United Fuel robot: logs in to cabinet.united-fuel.com, reads the Stations > List table (all pages),
and sends it to the app (POST /api/import/uf). The app geocodes new stations and stores discounted prices.
Credentials from .env (UF_USER, UF_PASS). Run: docker compose run --rm robot python unitedfuel.py"""
import os, re, httpx
from playwright.sync_api import sync_playwright
import common

URL = "https://cabinet.united-fuel.com"
APP = os.environ.get("APP_URL", "http://app:8000")
ROWS = "tbody tr.ant-table-row"

def read_page(pg):
    out = []
    for tr in pg.query_selector_all(ROWS):
        c = [x.inner_text().strip() for x in tr.query_selector_all("td")]
        if len(c) >= 7:
            out.append(dict(name=c[0], retail=c[1], price=c[2], updated=c[3], st=c[4], city=c[5], address=c[6]))
    return out

def login(pg):
    pg.get_by_placeholder("Email").fill(os.environ["UF_USER"]); common.pause()
    pg.locator("input[type=password]").first.fill(os.environ["UF_PASS"]); common.pause()
    pg.keyboard.press("Enter")

def main():
    common.gate("uf")
    with sync_playwright() as p:
        b, pg = common.open_session(p, "uf", URL + "/dashboard/station", r"/dashboard", login)
        common.pause(); pg.get_by_text("List", exact=True).first.click(); pg.wait_for_selector(ROWS, timeout=60000)
        pg.locator(".ant-pagination-options .ant-select").click()
        pg.get_by_text("100 / page").click(); pg.wait_for_timeout(2500)
        allrows, seen = [], set()
        for page_no in range(1, 60):
            rows = read_page(pg)
            new = [r for r in rows if r["name"] not in seen]
            for r in new: seen.add(r["name"])
            allrows += new
            print(f"page {page_no}: {len(rows)} rows, total {len(allrows)}", flush=True)
            nxt = pg.locator("li.ant-pagination-next")
            if nxt.get_attribute("aria-disabled") == "true": break
            common.pause(1.5, 4); nxt.click(); pg.wait_for_timeout(1500)
        b.close()
    print(f"read {len(allrows)} stations; sending to app (geocoding new ones can take a few minutes)")
    for i in range(0, len(allrows), 100):
        r = httpx.post(f"{APP}/api/import/uf", json=allrows[i:i + 100], timeout=600)
        r.raise_for_status(); print(r.json(), flush=True)

if __name__ == "__main__":
    main()
