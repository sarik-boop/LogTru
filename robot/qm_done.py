"""QuickManage completed loads (with the truck that hauled them) -> app database (done_loads). Not Airtable.
The completed-trips table is a virtual grid: the truck/driver column is off to the right, so each page is read twice
(scrolled left, then right) and the two halves are joined by row. A few pages only, newest first.
Run: docker compose run --rm robot python3 qm_done.py"""
import os, re, httpx
from playwright.sync_api import sync_playwright
import common
import quickmanage

URL = "https://app.quickmanage.com/dispatching/trips/main/completed?carrier_id=" + os.environ.get("QM_CARRIER_ID", "be691e25-9fe0-4549-8aad-ee4eb304e8c8")
PAGES = int(os.environ.get("QM_DONE_PAGES", "3"))
JS = """async()=>{const v=document.querySelector('.ag-center-cols-viewport');
 const grab=()=>{const m={};document.querySelectorAll('.ag-row').forEach(r=>{const i=r.getAttribute('row-index');(m[i]=m[i]||[]).push(r.innerText.replace(/\\s*\\n\\s*/g,' | '))});return m};
 v.scrollLeft=0;await new Promise(r=>setTimeout(r,1200));const L=grab();v.scrollLeft=99999;await new Promise(r=>setTimeout(r,1500));const R=grab();v.scrollLeft=0;
 return Object.keys(L).map(i=>({left:L[i].join(' '),right:(R[i]||[]).join(' ')}))}"""
TS = r"(\d\d/\d\d/\d{4} \d\d:\d\d \w+)"
MON = lambda s: float(s.replace(",", ""))

def parse_row(left, right):
    t = re.search(r"\b(\d{4,6})\b", left)
    if not t: return None
    st = re.search(r"\| (Delivered|Canceled|Invoiced|Dispatched|In Transit|Upcoming|Closed) \|", left) or re.search(r"(Delivered|Canceled)", left)
    o = re.search(r"\| 1 \| ([^|]+)\|[^|]*\|[^|]*\|\s*" + TS + r".*?\| 2 \| ([^|]+)\|[^|]*\|[^|]*\|\s*" + TS, left)
    bill = re.search(r"\| (?:NA|Invoiced|Paid|Partial[^|]*) \| (?:[\w-]+ \| )?([^|]+?) \| 1 \|", left)
    mi = re.search(r"([\d,.]+) mi \| ([\d,.]+) mi", left + " " + right)
    rate = re.search(r"\| \$([\d,]+\.\d\d) \| \$[\d.,]+/mi", left + " " + right)
    a = re.search(r"\$[\d,.]+ \| (\d{3,7}) \| ([A-Za-z][A-Za-z'.\- ]+?) \| (?:N/A|[A-Za-z])", right)
    if not o: return None
    return dict(trip=t.group(1), status=(st.group(1) if st else ""), bill_to=(bill.group(1).strip() if bill else ""),
                origin=o.group(1).strip(), o_time=o.group(2), dest=o.group(3).strip(), d_time=o.group(4),
                empty_mi=MON(mi.group(1)) if mi else None, loaded_mi=MON(mi.group(2)) if mi else None,
                rate=MON(rate.group(1)) if rate else None, truck=a.group(1) if a else "", driver=a.group(2).strip() if a else "")

def main():
    common.gate("qm", hours=os.environ.get("QM_HOURS", "6-22"))
    out = []
    with sync_playwright() as p:
        b, pg = common.open_session(p, "qm", URL, r"app\.quickmanage\.com/dispatching", quickmanage.login)
        for n in range(PAGES):
            try: pg.wait_for_selector(".ag-row", timeout=60000)
            except Exception: break
            pg.wait_for_timeout(3000)
            got = [r for r in (parse_row(x["left"], x["right"]) for x in pg.evaluate(JS)) if r]
            out += got; print(f"page {n}: {len(got)} loads", flush=True)
            nxt = pg.get_by_text("Next", exact=True).last
            if n + 1 >= PAGES or not nxt.count(): break
            nxt.click(); common.pause(2, 4)
        b.close()
    if not out: print("nothing read"); return
    r = httpx.post(os.environ.get("APP_URL", "http://app:8000") + "/api/done/import", json=out, timeout=120)
    r.raise_for_status(); print(r.json())

if __name__ == "__main__":
    main()
