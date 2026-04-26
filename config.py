"""
=============================================================
  TRADING BOT CONFIGURATION
  Edit this file to customize your bot.
=============================================================
"""

import os
from dotenv import load_dotenv
load_dotenv()

CONFIG = {
    # ── Exchange ─────────────────────────────────────────────
    # Any ccxt-supported exchange: 'binance', 'bybit', 'coinbase', 'kraken', etc.
    "exchange": os.getenv("EXCHANGE", "binance"),

    # API keys (only needed for private endpoints — not required for public OHLCV)
    "api_key":    os.getenv("EXCHANGE_API_KEY", ""),
    "api_secret": os.getenv("EXCHANGE_API_SECRET", ""),

    # ── Telegram ──────────────────────────────────────────────
    # 1. Create a bot via @BotFather on Telegram → get token
    # 2. Get your chat_id: message @userinfobot or use getUpdates API
    "telegram_token":   os.getenv("TELEGRAM_TOKEN", "YOUR_BOT_TOKEN_HERE"),
    "telegram_chat_id": os.getenv("TELEGRAM_CHAT_ID", "YOUR_CHAT_ID_HERE"),

    # ── Symbols to Watch ──────────────────────────────────────
    # Format: "BASE/QUOTE" for spot, "BASE/USDT:USDT" for futures (bybit/binance)
    "symbols": [
        "BTC/USDT",
        "ETH/USDT",
        "SOL/USDT",
        "BNB/USDT",
        "XRP/USDT",
    ],

    # ── Timeframes ────────────────────────────────────────────
    # Supported: '1m','5m','15m','30m','1h','4h','1d','1w'
    # Tip: 1h + 4h gives best signal quality for swing traders
    #      15m + 1h for day traders
    "timeframes": ["1h", "4h"],

    # ── Scan Interval ─────────────────────────────────────────
    # How often to scan markets (minutes).
    # Set to 15 for 15m TF, 60 for 1h TF, etc.
    "scan_interval_minutes": 60,

    # ── Signal Filtering ──────────────────────────────────────
    # Minimum strength score (0–100) to send a signal.
    # Recommended: 60 (quality), 70 (high quality), 80 (ultra-selective)
    "min_signal_strength": 65,

    # ── ATR-Based SL/TP Multipliers ───────────────────────────
    # These determine how far SL and TPs are from entry, based on ATR.
    # Example: ATR=100, sl_mult=1.5 → SL is 150 points from entry.
    "atr_sl_multiplier":  1.5,    # Stop Loss
    "atr_tp1_multiplier": 1.0,    # Take Profit 1 (quick exit, 1:0.67 R)
    "atr_tp2_multiplier": 2.0,    # Take Profit 2 (main target, 1:1.33 R)
    "atr_tp3_multiplier": 3.5,    # Take Profit 3 (runner, 1:2.33 R)
}
