import os, httpx

def send(text, chat_id=None):
    tok, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), chat_id or os.environ.get("TELEGRAM_CHAT_ID")
    if not tok or not chat:
        return dict(ok=False, error="TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set")
    r = httpx.post(f"https://api.telegram.org/bot{tok}/sendMessage", json=dict(chat_id=chat, text=text), timeout=30)
    return r.json()

def format_plan(load, origin, dest, p):
    lines = [f"Load {load}: {origin} -> {dest}", f"{p['miles']} mi, about {p['hours']} h driving"]
    f = p.get("fuel")
    if not f:
        lines.append("No fuel plan found (not enough station prices on the route).")
    else:
        lines.append(f"Planned fuel: ${f['cost']:,.0f} for {f['gallons']} gal")
        sc = p.get("schedule")
        if sc:
            lines.append(f"About {sc['total_h']} h door to door ({sc['drive_h']} h driving" + (f", {sc['sleeps']} overnight rest" if sc["sleeps"] else "") + ")")
            for e in sc["events"]:
                if e["kind"] == "fuel":
                    lines.append(f"- after {e['at']} h, mile {e['mile']}: {e['station']} ({e['city'].title()}, {e['st']}) buy {e['gallons']} gal at ${e['price']:.3f}")
                elif e["kind"] == "rest":
                    near = f" near {e['near']['city'].title()}, {e['near']['st']}" if e.get("near") else ""
                    lines.append(f"- after {e['at']} h, mile {e['mile']}: 10 h rest{near}")
                else:
                    lines.append(f"- after {e['at']} h: 30 min break")
        else:
            for s in f["plan"]:
                lines.append(f"- mile {s['mile']}: {s['station']} ({s['city'].title()}, {s['st']}) buy {s['gallons']} gal at ${s['price']:.3f}")
    if p.get("nav"): lines.append("Navigate: " + p["nav"])
    return "\n".join(lines)
