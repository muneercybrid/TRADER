"""
Interactive setup wizard — guides user through entering all credentials.
Writes values to .env file.
"""

import os
import re

ENV_FILE = ".env"

def read_env():
    env = {}
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()
    return env

def write_env(env: dict):
    lines = []
    with open(".env.example") as f:
        template = f.read()
    for line in template.splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or not stripped:
            lines.append(line)
        elif "=" in stripped:
            key = stripped.split("=")[0].strip()
            val = env.get(key, "")
            lines.append(f"{key}={val}")
        else:
            lines.append(line)
    with open(ENV_FILE, "w") as f:
        f.write("\n".join(lines) + "\n")

def ask(prompt: str, current: str = "", secret: bool = False, validate=None) -> str:
    display = f" [current: {'*****' if secret and current else current}]" if current else ""
    while True:
        val = input(f"  → {prompt}{display}\n    > ").strip()
        if not val and current:
            print(f"    ✅ Keeping existing value")
            return current
        if val:
            if validate and not validate(val):
                continue
            return val
        print("    ⚠️  This field is required. Please enter a value.")

def section(title: str):
    print(f"\n{'─'*44}")
    print(f"  {title}")
    print(f"{'─'*44}")

def main():
    env = read_env()

    print("  This wizard will set up your bot credentials.")
    print("  Press Enter to keep an existing value.")

    # ── TELEGRAM ─────────────────────────────────────────────
    section("📱 STEP 1 — Telegram Bot Token")
    print("""
  How to get your Telegram Bot Token:
  1. Open Telegram on your phone
  2. Search for:  @BotFather
  3. Send:        /newbot
  4. Choose a name (e.g. "My Trading Bot")
  5. Choose a username ending in 'bot' (e.g. "mytrading_bot")
  6. BotFather will reply with a token like:
     7123456789:AAFxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
  7. Copy that token and paste it below.
""")
    def validate_token(v):
        if re.match(r"^\d+:AA[A-Za-z0-9_-]{33,}$", v):
            return True
        print("    ⚠️  That doesn't look like a valid token. Format: 123456:AAFxxx...")
        return False

    token = ask("Paste your Telegram Bot Token",
                current=env.get("TELEGRAM_TOKEN", ""),
                secret=True,
                validate=validate_token)
    env["TELEGRAM_TOKEN"] = token

    # ── TELEGRAM CHAT ID ─────────────────────────────────────
    section("📱 STEP 2 — Telegram Chat ID")
    print(f"""
  How to get your Chat ID:
  1. Open Telegram and search for your new bot
     (the username you chose in Step 1)
  2. Send it any message (e.g. "hello")
  3. Open this URL in your browser:
     https://api.telegram.org/bot{token}/getUpdates
  4. Look for:  "chat":{{"id": XXXXXXXXX}}
  5. Copy that number (may be negative for groups — that's OK)
""")
    def validate_chatid(v):
        if re.match(r"^-?\d+$", v):
            return True
        print("    ⚠️  Chat ID should be a number (e.g. 987654321 or -100123456789)")
        return False

    chat_id = ask("Paste your Telegram Chat ID",
                  current=env.get("TELEGRAM_CHAT_ID", ""),
                  validate=validate_chatid)
    env["TELEGRAM_CHAT_ID"] = chat_id

    # ── EXCHANGE ─────────────────────────────────────────────
    section("🏦 STEP 3 — Exchange Selection")
    print("""
  Supported exchanges (no API key needed for signals):
    binance   — Binance (recommended, most liquid)
    bybit     — Bybit
    kraken    — Kraken
    kucoin    — KuCoin
    coinbase  — Coinbase

  Note: API keys are OPTIONAL for this bot.
  The bot only reads public market data (no trading).
  You only need keys if you want to place orders automatically.
""")
    exchanges = ["binance", "bybit", "kraken", "kucoin", "coinbase"]
    def validate_exchange(v):
        if v.lower() in exchanges:
            return True
        print(f"    ⚠️  Choose one of: {', '.join(exchanges)}")
        return False

    exchange = ask("Which exchange?",
                   current=env.get("EXCHANGE", "binance"),
                   validate=validate_exchange)
    env["EXCHANGE"] = exchange.lower()

    # ── API KEYS (optional) ───────────────────────────────────
    section("🔑 STEP 4 — Exchange API Keys (Optional)")
    print("""
  These are OPTIONAL. Leave blank if you only want signals.
  Only fill in if you want the bot to place trades automatically.

  If you want API keys later:
  1. Log into your exchange
  2. Go to Account → API Management
  3. Create a key with READ ONLY permissions (safest)
  4. Copy the API Key and Secret
""")
    want_keys = input("  → Do you want to add API keys now? (y/N) > ").strip().lower()
    if want_keys == "y":
        api_key = ask("Exchange API Key", current=env.get("EXCHANGE_API_KEY", ""), secret=True)
        env["EXCHANGE_API_KEY"] = api_key
        api_secret = ask("Exchange API Secret", current=env.get("EXCHANGE_API_SECRET", ""), secret=True)
        env["EXCHANGE_API_SECRET"] = api_secret
    else:
        print("    ✅ Skipped — bot will use public data only")

    # ── SAVE ─────────────────────────────────────────────────
    write_env(env)

    print(f"""
╔══════════════════════════════════════════╗
║   ✅ Configuration Saved to .env         ║
╠══════════════════════════════════════════╣
║                                          ║
║  Exchange:  {env.get('EXCHANGE','').ljust(30)} ║
║  Telegram:  Configured ✓                 ║
║  API Keys:  {'Set ✓' if env.get('EXCHANGE_API_KEY') else 'Not set (signals only)'.ljust(25)} ║
║                                          ║
║  Run your bot now:                       ║
║                                          ║
║    python bot.py                         ║
║                                          ║
╚══════════════════════════════════════════╝
""")

if __name__ == "__main__":
    main()
