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
        for s in f["plan"]:
            lines.append(f"- mile {s['mile']}: {s['station']} ({s['city'].title()}, {s['st']}) buy {s['gallons']} gal at ${s['price']:.3f}")
    if p.get("nav"): lines.append("Navigate: " + p["nav"])
    return "\n".join(lines)
