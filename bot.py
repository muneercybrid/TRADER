"""
=============================================================
  PROFESSIONAL TRADING SIGNAL BOT
  Multi-Indicator Confluence Engine + Telegram Delivery
=============================================================
  SETUP:
    pip install python-telegram-bot ccxt pandas ta requests schedule python-dotenv

  CONFIG: Edit config.py or set environment variables in .env
=============================================================
"""

import asyncio
import logging
import time
import schedule
import ccxt
import pandas as pd
import ta
import requests
import json
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Optional
from config import CONFIG

# ─── Logging ────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)


# ─── Data Structures ────────────────────────────────────────
@dataclass
class Signal:
    symbol: str
    timeframe: str
    direction: str          # BUY / SELL / NEUTRAL
    strength: int           # 0–100
    confidence: str         # LOW / MEDIUM / HIGH / VERY HIGH
    entry: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    take_profit_3: float
    indicators: dict = field(default_factory=dict)
    patterns: list = field(default_factory=list)
    reasons: list = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def rr_ratio(self):
        risk = abs(self.entry - self.stop_loss)
        reward = abs(self.take_profit_2 - self.entry)
        return round(reward / risk, 2) if risk else 0


# ─── Exchange / Data Feed ────────────────────────────────────
class MarketDataFeed:
    def __init__(self):
        exchange_id = CONFIG["exchange"]
        exchange_class = getattr(ccxt, exchange_id)
        self.exchange = exchange_class({
            "enableRateLimit": True,
            "apiKey": CONFIG.get("api_key", ""),
            "secret": CONFIG.get("api_secret", ""),
        })

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 300) -> pd.DataFrame:
        try:
            raw = self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
            df.set_index("timestamp", inplace=True)
            return df
        except Exception as e:
            log.error(f"fetch_ohlcv error [{symbol} {timeframe}]: {e}")
            return pd.DataFrame()

    def fetch_ticker(self, symbol: str) -> dict:
        try:
            return self.exchange.fetch_ticker(symbol)
        except Exception as e:
            log.error(f"fetch_ticker error [{symbol}]: {e}")
            return {}


# ─── Indicator Engine ────────────────────────────────────────
class IndicatorEngine:
    """Computes 15+ indicators and returns a scored confluence result."""

    def compute(self, df: pd.DataFrame) -> dict:
        if df.empty or len(df) < 100:
            return {}

        c = df["close"]
        h = df["high"]
        l = df["low"]
        v = df["volume"]

        result = {}

        # ── Trend Indicators ──────────────────────────────────
        # EMAs
        result["ema_8"]   = ta.trend.ema_indicator(c, 8).iloc[-1]
        result["ema_21"]  = ta.trend.ema_indicator(c, 21).iloc[-1]
        result["ema_50"]  = ta.trend.ema_indicator(c, 50).iloc[-1]
        result["ema_200"] = ta.trend.ema_indicator(c, 200).iloc[-1]
        result["price"]   = c.iloc[-1]

        # MACD
        macd_obj = ta.trend.MACD(c, window_slow=26, window_fast=12, window_sign=9)
        result["macd"]        = macd_obj.macd().iloc[-1]
        result["macd_signal"] = macd_obj.macd_signal().iloc[-1]
        result["macd_hist"]   = macd_obj.macd_diff().iloc[-1]
        result["macd_hist_prev"] = macd_obj.macd_diff().iloc[-2]

        # ADX
        adx_obj = ta.trend.ADXIndicator(h, l, c, window=14)
        result["adx"]    = adx_obj.adx().iloc[-1]
        result["di_pos"] = adx_obj.adx_pos().iloc[-1]
        result["di_neg"] = adx_obj.adx_neg().iloc[-1]

        # Supertrend (manual – ta library lacks it natively)
        result["supertrend"] = self._supertrend(df)

        # Ichimoku
        ichi = ta.trend.IchimokuIndicator(h, l, window1=9, window2=26, window3=52)
        result["ichi_a"]      = ichi.ichimoku_a().iloc[-1]
        result["ichi_b"]      = ichi.ichimoku_b().iloc[-1]
        result["ichi_base"]   = ichi.ichimoku_base_line().iloc[-1]
        result["ichi_conv"]   = ichi.ichimoku_conversion_line().iloc[-1]

        # ── Momentum Indicators ───────────────────────────────
        result["rsi"]  = ta.momentum.RSIIndicator(c, 14).rsi().iloc[-1]
        result["rsi_prev"] = ta.momentum.RSIIndicator(c, 14).rsi().iloc[-2]

        stoch = ta.momentum.StochasticOscillator(h, l, c, 14, 3)
        result["stoch_k"] = stoch.stoch().iloc[-1]
        result["stoch_d"] = stoch.stoch_signal().iloc[-1]

        result["cci"] = ta.trend.CCIIndicator(h, l, c, 20).cci().iloc[-1]
        result["mfi"] = ta.volume.MFIIndicator(h, l, c, v, 14).money_flow_index().iloc[-1]
        result["roc"] = ta.momentum.ROCIndicator(c, 12).roc().iloc[-1]

        # Williams %R
        result["willr"] = ta.momentum.WilliamsRIndicator(h, l, c, 14).williams_r().iloc[-1]

        # ── Volatility Indicators ─────────────────────────────
        bb = ta.volatility.BollingerBands(c, 20, 2)
        result["bb_upper"]  = bb.bollinger_hband().iloc[-1]
        result["bb_mid"]    = bb.bollinger_mavg().iloc[-1]
        result["bb_lower"]  = bb.bollinger_lband().iloc[-1]
        result["bb_width"]  = bb.bollinger_wband().iloc[-1]
        result["bb_pct"]    = bb.bollinger_pband().iloc[-1]

        result["atr"] = ta.volatility.AverageTrueRange(h, l, c, 14).average_true_range().iloc[-1]

        # ── Volume Indicators ─────────────────────────────────
        result["obv"]  = ta.volume.OnBalanceVolumeIndicator(c, v).on_balance_volume().iloc[-1]
        result["obv_prev"] = ta.volume.OnBalanceVolumeIndicator(c, v).on_balance_volume().iloc[-5]
        result["vwap"] = self._vwap(df)
        result["cmf"]  = ta.volume.ChaikinMoneyFlowIndicator(h, l, c, v, 20).chaikin_money_flow().iloc[-1]

        # Volume ratio vs 20-bar average
        vol_avg = v.rolling(20).mean().iloc[-1]
        result["vol_ratio"] = v.iloc[-1] / vol_avg if vol_avg else 1.0

        # ── Support / Resistance ──────────────────────────────
        result["support"]    = l.rolling(50).min().iloc[-1]
        result["resistance"] = h.rolling(50).max().iloc[-1]

        # ── Divergence ────────────────────────────────────────
        result["rsi_divergence"]  = self._check_divergence(c, ta.momentum.RSIIndicator(c, 14).rsi(), "rsi")
        result["macd_divergence"] = self._check_divergence(c, macd_obj.macd_diff(), "macd")

        return result

    def _supertrend(self, df: pd.DataFrame, period=10, multiplier=3.0) -> str:
        atr = ta.volatility.AverageTrueRange(df["high"], df["low"], df["close"], period).average_true_range()
        hl2 = (df["high"] + df["low"]) / 2
        upper = hl2 + multiplier * atr
        lower = hl2 - multiplier * atr
        close = df["close"]
        # Simplified: compare last close to bands
        if close.iloc[-1] > upper.iloc[-1]:
            return "BULLISH"
        elif close.iloc[-1] < lower.iloc[-1]:
            return "BEARISH"
        return "NEUTRAL"

    def _vwap(self, df: pd.DataFrame) -> float:
        typical = (df["high"] + df["low"] + df["close"]) / 3
        return (typical * df["volume"]).sum() / df["volume"].sum()

    def _check_divergence(self, price: pd.Series, indicator: pd.Series, name: str) -> str:
        """Detect regular bullish/bearish divergence over last 20 bars."""
        p = price.iloc[-20:]
        i = indicator.iloc[-20:]
        p_low_now, p_low_prev = p.iloc[-1], p.min()
        i_low_now, i_low_prev = i.iloc[-1], i.min()
        # Bullish: price makes lower low, indicator makes higher low
        if p_low_now < p_low_prev and i_low_now > i_low_prev:
            return "BULLISH"
        p_high_now, p_high_prev = p.iloc[-1], p.max()
        i_high_now, i_high_prev = i.iloc[-1], i.max()
        # Bearish: price makes higher high, indicator makes lower high
        if p_high_now > p_high_prev and i_high_now < i_high_prev:
            return "BEARISH"
        return "NONE"


# ─── Candlestick Pattern Detector ───────────────────────────
class PatternDetector:
    def detect(self, df: pd.DataFrame) -> list:
        if len(df) < 5:
            return []
        patterns = []
        o, h, l, c = df["open"], df["high"], df["low"], df["close"]
        o1, h1, l1, c1 = o.iloc[-1], h.iloc[-1], l.iloc[-1], c.iloc[-1]
        o2, h2, l2, c2 = o.iloc[-2], h.iloc[-2], l.iloc[-2], c.iloc[-2]
        o3, c3 = o.iloc[-3], c.iloc[-3]

        body1 = abs(c1 - o1)
        body2 = abs(c2 - o2)
        range1 = h1 - l1 or 0.0001
        upper_wick1 = h1 - max(o1, c1)
        lower_wick1 = min(o1, c1) - l1

        # Doji
        if body1 / range1 < 0.1:
            patterns.append("DOJI")

        # Hammer
        if lower_wick1 > 2 * body1 and upper_wick1 < body1 and c1 > o1:
            patterns.append("HAMMER 🔨")

        # Shooting Star
        if upper_wick1 > 2 * body1 and lower_wick1 < body1 and c1 < o1:
            patterns.append("SHOOTING_STAR ⭐")

        # Bullish Engulfing
        if c2 < o2 and c1 > o1 and c1 > o2 and o1 < c2:
            patterns.append("BULLISH_ENGULFING 🟢")

        # Bearish Engulfing
        if c2 > o2 and c1 < o1 and c1 < o2 and o1 > c2:
            patterns.append("BEARISH_ENGULFING 🔴")

        # Morning Star
        if c3 < o3 and body2 < abs(c3 - o3) * 0.3 and c1 > o1 and c1 > (o3 + c3) / 2:
            patterns.append("MORNING_STAR ☀️")

        # Evening Star
        if c3 > o3 and body2 < abs(c3 - o3) * 0.3 and c1 < o1 and c1 < (o3 + c3) / 2:
            patterns.append("EVENING_STAR 🌙")

        # Three White Soldiers
        if all(df["close"].iloc[-i] > df["open"].iloc[-i] for i in range(1, 4)):
            patterns.append("THREE_WHITE_SOLDIERS 💪")

        # Three Black Crows
        if all(df["close"].iloc[-i] < df["open"].iloc[-i] for i in range(1, 4)):
            patterns.append("THREE_BLACK_CROWS 🐦")

        return patterns


# ─── Signal Scorer ────────────────────────────────────────────
class SignalScorer:
    """
    Scores BUY/SELL strength 0–100 based on indicator confluence.
    Each indicator votes; weighted sum determines direction & strength.
    """

    def score(self, ind: dict, patterns: list) -> tuple[str, int, list]:
        buy_score = 0
        sell_score = 0
        reasons = []

        price = ind.get("price", 0)

        # ── EMA Stack (trend alignment) ───────────────────────
        if price > ind["ema_8"] > ind["ema_21"] > ind["ema_50"] > ind["ema_200"]:
            buy_score += 20
            reasons.append("✅ Full EMA bullish stack (8>21>50>200)")
        elif price < ind["ema_8"] < ind["ema_21"] < ind["ema_50"] < ind["ema_200"]:
            sell_score += 20
            reasons.append("✅ Full EMA bearish stack")
        elif price > ind["ema_21"] > ind["ema_50"]:
            buy_score += 10
            reasons.append("🟡 EMA 21/50 bullish")
        elif price < ind["ema_21"] < ind["ema_50"]:
            sell_score += 10
            reasons.append("🟡 EMA 21/50 bearish")

        # ── MACD ─────────────────────────────────────────────
        if ind["macd"] > ind["macd_signal"] and ind["macd_hist"] > 0 and ind["macd_hist"] > ind["macd_hist_prev"]:
            buy_score += 15
            reasons.append("✅ MACD bullish crossover + expanding histogram")
        elif ind["macd"] < ind["macd_signal"] and ind["macd_hist"] < 0 and ind["macd_hist"] < ind["macd_hist_prev"]:
            sell_score += 15
            reasons.append("✅ MACD bearish crossover + expanding histogram")

        # ── RSI ───────────────────────────────────────────────
        rsi = ind["rsi"]
        if 50 < rsi < 70 and ind["rsi"] > ind["rsi_prev"]:
            buy_score += 10
            reasons.append(f"✅ RSI bullish momentum ({rsi:.1f})")
        elif 30 < rsi < 50 and ind["rsi"] < ind["rsi_prev"]:
            sell_score += 10
            reasons.append(f"✅ RSI bearish momentum ({rsi:.1f})")
        elif rsi < 30:
            buy_score += 8
            reasons.append(f"🟡 RSI oversold ({rsi:.1f})")
        elif rsi > 70:
            sell_score += 8
            reasons.append(f"🟡 RSI overbought ({rsi:.1f})")

        # ── Stochastic ────────────────────────────────────────
        sk, sd = ind["stoch_k"], ind["stoch_d"]
        if sk > sd and sk < 80 and sd < 80:
            buy_score += 8
            reasons.append(f"✅ Stochastic bullish ({sk:.0f}/{sd:.0f})")
        elif sk < sd and sk > 20 and sd > 20:
            sell_score += 8
            reasons.append(f"✅ Stochastic bearish ({sk:.0f}/{sd:.0f})")
        elif sk < 20:
            buy_score += 5
            reasons.append(f"🟡 Stochastic oversold ({sk:.0f})")
        elif sk > 80:
            sell_score += 5
            reasons.append(f"🟡 Stochastic overbought ({sk:.0f})")

        # ── ADX (trend strength) ──────────────────────────────
        adx = ind["adx"]
        if adx > 25:
            if ind["di_pos"] > ind["di_neg"]:
                buy_score += 10
                reasons.append(f"✅ ADX {adx:.1f} strong uptrend")
            else:
                sell_score += 10
                reasons.append(f"✅ ADX {adx:.1f} strong downtrend")
        else:
            reasons.append(f"⚠️ ADX {adx:.1f} weak trend — range market")

        # ── Supertrend ────────────────────────────────────────
        if ind["supertrend"] == "BULLISH":
            buy_score += 10
            reasons.append("✅ Supertrend BULLISH")
        elif ind["supertrend"] == "BEARISH":
            sell_score += 10
            reasons.append("✅ Supertrend BEARISH")

        # ── Bollinger Bands ───────────────────────────────────
        bp = ind["bb_pct"]
        if bp < 0.2:
            buy_score += 7
            reasons.append(f"✅ Price near BB lower band (oversold squeeze)")
        elif bp > 0.8:
            sell_score += 7
            reasons.append(f"✅ Price near BB upper band (overbought squeeze)")

        # ── VWAP ──────────────────────────────────────────────
        if price > ind["vwap"]:
            buy_score += 5
            reasons.append("✅ Price above VWAP")
        else:
            sell_score += 5
            reasons.append("✅ Price below VWAP")

        # ── CCI ───────────────────────────────────────────────
        cci = ind["cci"]
        if cci > 100:
            buy_score += 5
            reasons.append(f"✅ CCI bullish momentum ({cci:.0f})")
        elif cci < -100:
            sell_score += 5
            reasons.append(f"✅ CCI bearish momentum ({cci:.0f})")

        # ── MFI ───────────────────────────────────────────────
        mfi = ind["mfi"]
        if mfi < 20:
            buy_score += 6
            reasons.append(f"✅ MFI oversold ({mfi:.0f}) — buying pressure incoming")
        elif mfi > 80:
            sell_score += 6
            reasons.append(f"✅ MFI overbought ({mfi:.0f}) — selling pressure incoming")

        # ── CMF ───────────────────────────────────────────────
        cmf = ind["cmf"]
        if cmf > 0.1:
            buy_score += 5
            reasons.append(f"✅ CMF positive ({cmf:.2f}) — accumulation")
        elif cmf < -0.1:
            sell_score += 5
            reasons.append(f"✅ CMF negative ({cmf:.2f}) — distribution")

        # ── OBV Trend ─────────────────────────────────────────
        if ind["obv"] > ind["obv_prev"]:
            buy_score += 5
            reasons.append("✅ OBV rising — volume confirms uptrend")
        else:
            sell_score += 5
            reasons.append("✅ OBV falling — volume confirms downtrend")

        # ── Volume Confirmation ───────────────────────────────
        vr = ind["vol_ratio"]
        if vr > 1.5:
            bonus = min(10, int(vr * 3))
            if buy_score > sell_score:
                buy_score += bonus
            else:
                sell_score += bonus
            reasons.append(f"🔥 High volume spike ({vr:.1f}x avg) confirms move")

        # ── Divergence ────────────────────────────────────────
        if ind["rsi_divergence"] == "BULLISH":
            buy_score += 8
            reasons.append("🔍 RSI bullish divergence detected")
        elif ind["rsi_divergence"] == "BEARISH":
            sell_score += 8
            reasons.append("🔍 RSI bearish divergence detected")

        if ind["macd_divergence"] == "BULLISH":
            buy_score += 5
            reasons.append("🔍 MACD bullish divergence detected")
        elif ind["macd_divergence"] == "BEARISH":
            sell_score += 5
            reasons.append("🔍 MACD bearish divergence detected")

        # ── Ichimoku ──────────────────────────────────────────
        if price > ind["ichi_a"] and price > ind["ichi_b"] and ind["ichi_conv"] > ind["ichi_base"]:
            buy_score += 8
            reasons.append("✅ Price above Ichimoku cloud — bull")
        elif price < ind["ichi_a"] and price < ind["ichi_b"] and ind["ichi_conv"] < ind["ichi_base"]:
            sell_score += 8
            reasons.append("✅ Price below Ichimoku cloud — bear")

        # ── Candlestick Patterns ──────────────────────────────
        for p in patterns:
            if any(x in p for x in ["HAMMER", "BULLISH_ENGULFING", "MORNING_STAR", "THREE_WHITE"]):
                buy_score += 5
                reasons.append(f"🕯️ Pattern: {p}")
            elif any(x in p for x in ["SHOOTING_STAR", "BEARISH_ENGULFING", "EVENING_STAR", "THREE_BLACK"]):
                sell_score += 5
                reasons.append(f"🕯️ Pattern: {p}")

        # ── Determine direction ───────────────────────────────
        total = buy_score + sell_score or 1
        if buy_score > sell_score and buy_score > 30:
            strength = min(100, int((buy_score / total) * 100 + (buy_score / 10)))
            return "BUY", strength, reasons
        elif sell_score > buy_score and sell_score > 30:
            strength = min(100, int((sell_score / total) * 100 + (sell_score / 10)))
            return "SELL", strength, reasons

        return "NEUTRAL", 0, reasons


# ─── Signal Builder ───────────────────────────────────────────
class SignalBuilder:
    def build(self, symbol: str, timeframe: str, ind: dict,
              direction: str, strength: int, patterns: list, reasons: list) -> Optional[Signal]:
        if direction == "NEUTRAL" or strength < CONFIG["min_signal_strength"]:
            return None

        price = ind["price"]
        atr = ind["atr"]

        # Dynamic SL/TP using ATR multipliers
        sl_mult  = CONFIG["atr_sl_multiplier"]
        tp1_mult = CONFIG["atr_tp1_multiplier"]
        tp2_mult = CONFIG["atr_tp2_multiplier"]
        tp3_mult = CONFIG["atr_tp3_multiplier"]

        if direction == "BUY":
            sl  = price - atr * sl_mult
            tp1 = price + atr * tp1_mult
            tp2 = price + atr * tp2_mult
            tp3 = price + atr * tp3_mult
        else:
            sl  = price + atr * sl_mult
            tp1 = price - atr * tp1_mult
            tp2 = price - atr * tp2_mult
            tp3 = price - atr * tp3_mult

        confidence_map = {
            (0,  50):  "LOW",
            (50, 65):  "MEDIUM",
            (65, 80):  "HIGH",
            (80, 101): "VERY HIGH",
        }
        confidence = next(v for (lo, hi), v in confidence_map.items() if lo <= strength < hi)

        return Signal(
            symbol=symbol,
            timeframe=timeframe,
            direction=direction,
            strength=strength,
            confidence=confidence,
            entry=round(price, 6),
            stop_loss=round(sl, 6),
            take_profit_1=round(tp1, 6),
            take_profit_2=round(tp2, 6),
            take_profit_3=round(tp3, 6),
            indicators=ind,
            patterns=patterns,
            reasons=reasons,
        )


# ─── Telegram Notifier ────────────────────────────────────────
class TelegramNotifier:
    def __init__(self):
        self.token   = CONFIG["telegram_token"]
        self.chat_id = CONFIG["telegram_chat_id"]
        self.base    = f"https://api.telegram.org/bot{self.token}"

    def send(self, signal: Signal):
        msg = self._format(signal)
        url = f"{self.base}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": msg,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        try:
            r = requests.post(url, json=payload, timeout=10)
            if r.status_code == 200:
                log.info(f"Telegram: sent {signal.direction} signal for {signal.symbol}")
            else:
                log.error(f"Telegram error: {r.text}")
        except Exception as e:
            log.error(f"Telegram send failed: {e}")

    def send_text(self, text: str):
        url = f"{self.base}/sendMessage"
        requests.post(url, json={"chat_id": self.chat_id, "text": text,
                                 "parse_mode": "HTML"}, timeout=10)

    def _format(self, s: Signal) -> str:
        emoji = "🟢" if s.direction == "BUY" else "🔴"
        stars = "⭐" * (s.strength // 20)
        ind = s.indicators

        reasons_text = "\n".join(f"  • {r}" for r in s.reasons[:10])
        patterns_text = ", ".join(s.patterns) if s.patterns else "None"

        return f"""
{emoji}<b>{s.direction} SIGNAL — {s.symbol}</b> [{s.timeframe}]
━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎯 <b>Confidence:</b> {s.confidence}  {stars}
📊 <b>Strength:</b> {s.strength}/100
⏰ <b>Time:</b> {s.timestamp.strftime('%Y-%m-%d %H:%M UTC')}

💰 <b>ENTRY:</b>  <code>{s.entry}</code>
🛑 <b>STOP:</b>   <code>{s.stop_loss}</code>
🎯 <b>TP1:</b>    <code>{s.take_profit_1}</code>
🎯 <b>TP2:</b>    <code>{s.take_profit_2}</code>
🎯 <b>TP3:</b>    <code>{s.take_profit_3}</code>
📐 <b>R:R Ratio:</b> 1:{s.rr_ratio()}

━━━━━━━━━━━━━━━━━━━━━━━━━━━
📈 <b>KEY INDICATORS</b>
  RSI: {ind.get('rsi',0):.1f}  |  MACD Hist: {ind.get('macd_hist',0):.4f}
  ADX: {ind.get('adx',0):.1f}  |  ATR: {ind.get('atr',0):.4f}
  MFI: {ind.get('mfi',0):.1f}  |  CMF: {ind.get('cmf',0):.3f}
  Vol Ratio: {ind.get('vol_ratio',1):.1f}x

🕯️ <b>PATTERNS:</b> {patterns_text}

📋 <b>REASONS ({len(s.reasons)}):</b>
{reasons_text}

━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ <i>Not financial advice. Use proper risk management.</i>
""".strip()


# ─── Main Bot Loop ────────────────────────────────────────────
class TradingBot:
    def __init__(self):
        self.feed      = MarketDataFeed()
        self.engine    = IndicatorEngine()
        self.detector  = PatternDetector()
        self.scorer    = SignalScorer()
        self.builder   = SignalBuilder()
        self.notifier  = TelegramNotifier()
        self.sent: dict[str, str] = {}  # symbol -> last direction sent

    def run_scan(self):
        log.info("━" * 50)
        log.info(f"Running scan — {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}")
        signals_found = 0

        for symbol in CONFIG["symbols"]:
            for tf in CONFIG["timeframes"]:
                try:
                    df = self.feed.fetch_ohlcv(symbol, tf)
                    if df.empty:
                        continue

                    ind      = self.engine.compute(df)
                    if not ind:
                        continue

                    patterns = self.detector.detect(df)
                    direction, strength, reasons = self.scorer.score(ind, patterns)
                    signal = self.builder.build(symbol, tf, ind, direction, strength, patterns, reasons)

                    if signal:
                        key = f"{symbol}_{tf}"
                        last = self.sent.get(key)
                        if last != signal.direction:  # avoid spam
                            self.notifier.send(signal)
                            self.sent[key] = signal.direction
                            signals_found += 1
                            log.info(f"  → {signal.direction} {symbol} [{tf}] strength={strength}")
                        else:
                            log.info(f"  ↺ Skipped duplicate {signal.direction} {symbol} [{tf}]")
                    else:
                        log.info(f"  — No signal: {symbol} [{tf}] ({direction})")

                    time.sleep(0.3)  # Rate limit

                except Exception as e:
                    log.error(f"Error processing {symbol} [{tf}]: {e}", exc_info=True)

        log.info(f"Scan complete — {signals_found} signal(s) dispatched")

    def start(self):
        log.info("=" * 50)
        log.info("  TRADING SIGNAL BOT STARTED")
        log.info(f"  Symbols:    {CONFIG['symbols']}")
        log.info(f"  Timeframes: {CONFIG['timeframes']}")
        log.info(f"  Exchange:   {CONFIG['exchange']}")
        log.info(f"  Interval:   every {CONFIG['scan_interval_minutes']} min")
        log.info("=" * 50)

        self.notifier.send_text("🤖 <b>Trading Bot Started</b>\nMonitoring markets...")
        self.run_scan()

        schedule.every(CONFIG["scan_interval_minutes"]).minutes.do(self.run_scan)
        while True:
            schedule.run_pending()
            time.sleep(10)


if __name__ == "__main__":
    bot = TradingBot()
    bot.start()
