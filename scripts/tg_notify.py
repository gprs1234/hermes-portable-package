#!/usr/bin/env python3
"""Send Telegram notification via bot API.
Usage: python3 tg_notify.py "message text"
"""
import urllib.request, json, pathlib, sys

def get_token():
    env = pathlib.Path.home() / '.hermes/.env'
    if not env.exists():
        return ""
    lines = env.read_text().splitlines()
    # Preferred: HERMES_BOT_TOKEN (�j�� bot)
    for line in lines:
        line = line.strip()
        if line.startswith('HERMES_BOT_TOKEN=') and not line.startswith('#'):
            return line.split('=', 1)[1].strip().strip('"').strip("'")
    # Compatible fallback: TELEGRAM_BOT_TOKEN should also point to �j�� bot.
    for line in lines:
        line = line.strip()
        if line.startswith('TELEGRAM_BOT_TOKEN=') and not line.startswith('#'):
            return line.split('=', 1)[1].strip().strip('"').strip("'")
    return ""

def send(msg, chat_id="6823341162"):
    token = get_token()
    if not token:
        print("ERROR: No HERMES_BOT_TOKEN or TELEGRAM_BOT_TOKEN")
        return False
    body = json.dumps({"chat_id": chat_id, "text": msg}).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read())
        return data.get("ok", False)
    except Exception as e:
        print(f"ERROR: {e}")
        return False

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: tg_notify.py 'message'")
        sys.exit(1)
    msg = " ".join(sys.argv[1:])
    ok = send(msg)
    print("Sent" if ok else "Failed")
