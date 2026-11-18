"""Shared 'polite robot' rules: reuse one saved login, few requests, random timing, business hours,
and a cool-down after a failed login so a wrong password can never cause repeated attempts / account lockout."""
import os, re, sys, time, random
from pathlib import Path
from zoneinfo import ZoneInfo
import datetime as dt

STATE = Path(os.environ.get("ROBOT_STATE", "/state"))
COOLDOWN_H = 6

def pause(a=0.8, b=2.5):
    time.sleep(random.uniform(a, b))

def gate(name, hours=None):
    """Call first. Exits quietly if cooling down or outside business hours; adds random start delay when scheduled."""
    STATE.mkdir(parents=True, exist_ok=True)
    cd = STATE / f"{name}.cooldown"
    if cd.exists():
        age = (time.time() - cd.stat().st_mtime) / 3600
        if age < COOLDOWN_H:
            sys.exit(f"{name}: login failed {age:.1f}h ago; not retrying for {COOLDOWN_H}h. Fix credentials, then delete {cd}.")
    if hours:
        lo, hi = map(int, hours.split("-"))
        now = dt.datetime.now(ZoneInfo(os.environ.get("ROBOT_TZ", "America/Chicago")))
        if not (lo <= now.hour < hi) or now.weekday() == 6:
            sys.exit(f"{name}: outside business hours ({hours}, Mon-Sat), skipping.")
    if os.environ.get("ROBOT_JITTER"):                       # set by the scheduler, not by manual runs
        time.sleep(random.uniform(0, int(os.environ.get("ROBOT_JITTER_MAX", "600"))))

def open_session(p, name, url, ok_re, login):
    """Open `url` using the saved session; log in only if the site sends us elsewhere. Returns (browser, page)."""
    b = p.chromium.launch()
    sf = STATE / f"{name}.json"
    ctx = b.new_context(storage_state=str(sf) if sf.exists() else None, viewport={"width": 1500, "height": 900}, locale="en-US")
    pg = ctx.new_page(); pg.goto(url); pause(2, 4)
    if not re.search(ok_re, pg.url):
        print(f"{name}: saved session missing/expired, logging in once", flush=True)
        try:
            login(pg); pg.wait_for_url(re.compile(ok_re), timeout=60000)
        except Exception as e:
            (STATE / f"{name}.cooldown").touch(); b.close()
            sys.exit(f"{name}: login failed ({e}). Cooling down {COOLDOWN_H}h, no further attempts.")
        ctx.storage_state(path=str(sf)); os.chmod(sf, 0o600)
        (STATE / f"{name}.cooldown").unlink(missing_ok=True)
        pg.goto(url); pause(2, 4)
    return b, pg
