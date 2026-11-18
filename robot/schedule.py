"""Tiny scheduler: runs each robot once a day at a fixed local time (America/Chicago by default) with a random start delay.
Remembers the last run in /state so a restart never repeats a run. Add jobs to JOBS."""
import os, json, time, subprocess, datetime as dt
from zoneinfo import ZoneInfo
from pathlib import Path

TZ = ZoneInfo(os.environ.get("ROBOT_TZ", "America/Chicago"))
STATE = Path(os.environ.get("ROBOT_STATE", "/state")) / "schedule.json"
JOBS = [  # (name, script, hour, minute) once a day
    ("united-fuel", "unitedfuel.py", int(os.environ.get("UF_HOUR", "5")), 30),
    ("qm-fuel", "qm_fuel.py", int(os.environ.get("QMFUEL_HOUR", "7")), 10),
]
EVERY = [  # (name, script, minutes) repeating; the robots themselves only run 06-22 Chicago, Mon-Sat
    ("qm-loads", "quickmanage.py", int(os.environ.get("QM_LOADS_MIN", "60"))),
    ("qm-done", "qm_done.py", int(os.environ.get("QM_DONE_MIN", "60"))),
]

def load():
    try: return json.loads(STATE.read_text())
    except Exception: return {}

def main():
    print("scheduler started: " + ", ".join(f"{n} every {m} min" for n,_,m in EVERY) + ", " + ", ".join(f"{n} daily {h:02d}:{m:02d} {TZ.key}" for n, _, h, m in JOBS), flush=True)
    while True:
        now = dt.datetime.now(TZ); last = load()
        for name, script, h, m in JOBS:
            due = now.replace(hour=h, minute=m, second=0, microsecond=0)
            if now >= due and last.get(name) != now.date().isoformat() and (now - due).total_seconds() < 6 * 3600:
                last[name] = now.date().isoformat(); STATE.write_text(json.dumps(last))
                print(f"{now:%F %T} running {name}", flush=True)
                r = subprocess.run(["python3", script], env={**os.environ, "ROBOT_JITTER": "1"})
                print(f"{name} finished with code {r.returncode}", flush=True)
        for name, script, mins in EVERY:
            if time.time() - float(last.get(name + ".ts", 0)) >= mins * 60:
                last[name + ".ts"] = time.time(); STATE.write_text(json.dumps(last))
                print(f"{now:%F %T} running {name}", flush=True)
                r = subprocess.run(["python3", script], env={**os.environ, "ROBOT_JITTER": "1", "ROBOT_JITTER_MAX": "120"})
                print(f"{name} finished with code {r.returncode}", flush=True)
        time.sleep(60)

if __name__ == "__main__":
    main()
