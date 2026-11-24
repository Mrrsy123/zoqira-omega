from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any
import json
import math

from market_data import fetch_ohlcv, get_current_price, normalize_symbol
from analysis import compute_full_analysis
from config import MARKETS, Market


@dataclass
class TradingSignal:
    symbol: str
    direction: str  # BUY, SELL, NEUTRAL
    entry_price: float
    stop_loss: float
    take_profit: float
    take_profit_1: float
    take_profit_2: float
    take_profit_3: float
    confidence: int  # 0-100
    risk_reward: float
    risk_amount: float
    risk_pct: float
    reward_amount: float
    reward_pct: float
    timeframe: str
    indicators: dict
    summary: str
    summary_kh: str
    key_reasons: List[str]
    atr_data: Optional[dict]
    support_resistance: Optional[dict]
    # Optimal Entry Fields
    optimal_entry_min: float = 0.0
    optimal_entry_max: float = 0.0
    optimal_entry_target: float = 0.0
    is_optimal_now: bool = False
    entry_timing_status: str = ""
    entry_timing_kh: str = ""
    entry_technique: str = ""
    market_name: str = ""
    category: str = ""
    emoji: str = ""


def calculate_risk_reward(entry: float, sl: float, tp: float, direction: str) -> tuple[float, float, float, float, float]:
    """Calculate risk amount, reward amount, %, and R:R ratio."""
    if direction == "BUY":
        risk = max(entry - sl, 0.0001)
        reward = max(tp - entry, 0.0001)
    elif direction == "SELL":
        risk = max(sl - entry, 0.0001)
        reward = max(entry - tp, 0.0001)
    else:
        return 0.0, 0.0, 0.0, 0.0, 0.0

    risk_pct = round((risk / entry) * 100, 2) if entry > 0 else 0.0
    reward_pct = round((reward / entry) * 100, 2) if entry > 0 else 0.0
    rr = round(reward / risk, 2) if risk > 0 else 0.0
    return round(risk, 4), risk_pct, round(reward, 4), reward_pct, rr


def calculate_lot_size(account_balance: float, risk_percent: float, entry: float, sl: float, symbol: str) -> Dict[str, Any]:
    """Calculate recommended lot size and position sizing based on risk percentage."""
    if entry <= 0 or sl <= 0 or entry == sl:
        return {"lot_size": 0.01, "risk_dollar": 0.0, "position_value": 0.0}

    risk_dollar = round(account_balance * (risk_percent / 100), 2)
    sl_distance = abs(entry - sl)

    symbol_upper = symbol.upper()
    if "XAU" in symbol_upper or "GC" in symbol_upper:
        dollars_per_lot_risk = sl_distance * 100
        lot_size = risk_dollar / dollars_per_lot_risk if dollars_per_lot_risk > 0 else 0.01
    elif "BTC" in symbol_upper or "ETH" in symbol_upper:
        lot_size = risk_dollar / sl_distance if sl_distance > 0 else 0.01
    else:
        lot_size = risk_dollar / sl_distance if sl_distance > 0 else 0.01

    return {
        "lot_size": max(round(lot_size, 2), 0.01),
        "risk_dollar": risk_dollar,
        "sl_distance": round(sl_distance, 4),
        "potential_gain_tp1": round((risk_dollar * 1.0), 2),
        "potential_gain_tp2": round((risk_dollar * 1.8), 2),
        "potential_gain_tp3": round((risk_dollar * 2.5), 2),
    }


def generate_signal(symbol_name: str, timeframe: str = "1h") -> Optional[TradingSignal]:
    """Generate an AI trading signal with precision Optimal Trade Entry (OTE) detection."""
    symbol_name = normalize_symbol(symbol_name)
    if symbol_name not in MARKETS:
        return None

    market = MARKETS[symbol_name]

    tf_map = {
        "15m": ("15m", "5d"),
        "1h": ("1h", "30d"),
        "4h": ("1h", "60d"),
        "1d": ("1d", "90d"),
    }
    interval, period = tf_map.get(timeframe, ("1h", "30d"))

    df = fetch_ohlcv(symbol_name, interval=interval, period=period)
    if df is None or df.empty or len(df) < 20:
        return None

    analysis = compute_full_analysis(df)
    signals = analysis.get("signals", {})
    atr_data = analysis.get("atr", {})
    sr = analysis.get("support_resistance", {})
    last_price = float(analysis.get("last_price", df.iloc[-1]["Close"]))
    df_ind = analysis.get("df", df)

    if "error" in signals:
        return None

    # Weighted Scoring System
    weights = {
        "RSI": 1.6,
        "MACD": 1.4,
        "EMA": 1.5,
        "BB": 0.9,
        "ADX": 1.2,
        "STOCH": 0.9,
        "TREND_LONG": 1.3,
        "VOLUME": 0.7,
    }

    buy_score = 0.0
    sell_score = 0.0
    total_weight = 0.0

    for indicator, data in signals.items():
        w = weights.get(indicator, 1.0)
        total_weight += w
        sig = data.get("signal", "NEUTRAL")
        if sig == "BUY":
            buy_score += w
        elif sig == "SELL":
            sell_score += w

    max_score = max(buy_score, sell_score)
    if total_weight > 0:
        confidence = min(round((max_score / total_weight) * 100), 96)
    else:
        confidence = 50

    if buy_score > sell_score:
        direction = "BUY"
    elif sell_score > buy_score:
        direction = "SELL"
    else:
        direction = "NEUTRAL"

    # Divergence / mixed signal dampener
    if min(buy_score, sell_score) > 0 and max_score > 0:
        ratio_diff = abs(buy_score - sell_score) / max_score
        if ratio_diff < 0.25:
            direction = "NEUTRAL"
            confidence = max(round(confidence * 0.65), 35)

    # Stop Loss & Multi-Take Profit Targets via ATR
    atr_val = atr_data["ATR"] if (atr_data and atr_data.get("ATR")) else (last_price * 0.008)

    # ==================== Optimal Trade Entry (OTE) Calculation ====================
    # Find EMA 21 and recent swing levels
    ema_21 = float(df_ind.iloc[-1].get("EMA_21", last_price))
    support = float(sr.get("support", last_price * 0.99))
    resistance = float(sr.get("resistance", last_price * 1.01))

    if direction == "BUY":
        stop_loss = round(last_price - (atr_val * 1.5), 4)
        tp1 = round(last_price + (atr_val * 1.2), 4)
        tp2 = round(last_price + (atr_val * 2.0), 4)
        tp3 = round(last_price + (atr_val * 3.0), 4)
        take_profit = tp2

        # Optimal Entry Zone for BUY: Retracement to EMA 21 / Support (Buy Low, not at the top of wick)
        optimal_target = float(round(min(last_price, max(ema_21, support, last_price - (atr_val * 0.25))), 4))
        optimal_min = float(round(optimal_target - (atr_val * 0.15), 4))
        optimal_max = float(round(optimal_target + (atr_val * 0.15), 4))

        # Check if current price is in optimal zone
        dist_from_optimal = abs(last_price - optimal_target)
        is_optimal = bool(dist_from_optimal <= (atr_val * 0.2) or last_price <= optimal_max)

        if is_optimal:
            timing_status = "READY_TO_ENTER"
            timing_kh = "🎯 តម្លៃដល់កម្រិតល្អបំផុតហើយ (OPTIMAL ENTRY) — អាចចូល BUY បាន!"
            entry_technique = "Pullback to Key Support / EMA 21 Zone"
        else:
            timing_status = "WAIT_FOR_PULLBACK"
            timing_kh = f"⏳ តម្លៃឡើងខ្ពស់បន្តិច រង់ចាំទាញថយក្រោយមកតំបន់ ${optimal_target:,.2f} សិនទើបចូល Buy"
            entry_technique = "Waiting for Retracement / Dip"

    elif direction == "SELL":
        stop_loss = round(last_price + (atr_val * 1.5), 4)
        tp1 = round(last_price - (atr_val * 1.2), 4)
        tp2 = round(last_price - (atr_val * 2.0), 4)
        tp3 = round(last_price - (atr_val * 3.0), 4)
        take_profit = tp2

        # Optimal Entry Zone for SELL: Retracement rally up into EMA 21 / Resistance (Sell High)
        optimal_target = float(round(max(last_price, min(ema_21, resistance, last_price + (atr_val * 0.25))), 4))
        optimal_min = float(round(optimal_target - (atr_val * 0.15), 4))
        optimal_max = float(round(optimal_target + (atr_val * 0.15), 4))

        # Check if current price is in optimal zone
        dist_from_optimal = abs(last_price - optimal_target)
        is_optimal = bool(dist_from_optimal <= (atr_val * 0.2) or last_price >= optimal_min)

        if is_optimal:
            timing_status = "READY_TO_ENTER"
            timing_kh = "🎯 តម្លៃឡើងមកដល់កម្រិតល្អបំផុតហើយ (OPTIMAL ENTRY) — អាចចូល SELL បាន!"
            entry_technique = "Bounce into Resistance / EMA 21 Zone"
        else:
            timing_status = "WAIT_FOR_PULLBACK"
            timing_kh = f"⏳ តម្លៃធ្លាក់ច្រើនហើយ រង់ចាំទាញឡើងមកតំបន់ ${optimal_target:,.2f} សិនទើបចូល Sell"
            entry_technique = "Waiting for Rally / Retracement"
    else:
        stop_loss = round(last_price * 0.99, 4)
        tp1 = round(last_price * 1.01, 4)
        tp2 = round(last_price * 1.02, 4)
        tp3 = round(last_price * 1.03, 4)
        take_profit = tp2
        optimal_min = float(round(last_price * 0.998, 4))
        optimal_max = float(round(last_price * 1.002, 4))
        optimal_target = float(round(last_price, 4))
        is_optimal = False
        timing_status = "MARKET_CONSOLIDATING"
        timing_kh = "⏸️ ទីផ្សារគ្មាន Trend — រង់ចាំទម្លាយ Breakout សិន"
        entry_technique = "Neutral Market / Range Bound"

    risk, risk_pct, reward, reward_pct, rr = calculate_risk_reward(last_price, stop_loss, take_profit, direction)

    # Key Reasons
    strong_signals = [k for k, v in signals.items() if v.get("signal") == direction]
    key_reasons = [f"{k}: {signals[k]['reason']}" for k in strong_signals]

    # Summary in Khmer
    dir_kh = "ទិញ (BUY / LONG)" if direction == "BUY" else "លក់ (SELL / SHORT)" if direction == "SELL" else "រង់ចាំ (NEUTRAL / WAIT)"
    strength_kh = "ខ្លាំង (Strong)" if confidence >= 75 else "មធ្យម (Moderate)" if confidence >= 55 else "ខ្សោយ (Weak)"

    if direction == "NEUTRAL":
        summary_kh = f"ទីផ្សារស្ថិតក្នុងសភាពចំហៀង (Sideway / Range-bound)។ សញ្ញាបច្ចេកទេសចម្រុះគ្នា មិនទាន់មាន Trend ច្បាស់លាស់ឡើយ — គួររង់ចាំ Breakout។"
        summary_en = f"Market is currently consolidating. Mixed technical indicators suggest waiting for confirmation before entry."
    else:
        summary_kh = f"សញ្ញា {dir_kh} កម្រិត {strength_kh} ជាមួយទំនុកចិត្ត {confidence}%។ R:R ស្មើ 1:{rr} (Reward {reward_pct}% ធៀប Risk {risk_pct}%)។"
        summary_en = f"{direction} signal with {strength_kh} strength ({confidence}% confidence). Favorable Risk/Reward 1:{rr}."

    return TradingSignal(
        symbol=symbol_name,
        direction=direction,
        entry_price=round(last_price, 4),
        stop_loss=stop_loss,
        take_profit=take_profit,
        take_profit_1=tp1,
        take_profit_2=tp2,
        take_profit_3=tp3,
        confidence=confidence,
        risk_reward=rr,
        risk_amount=risk,
        risk_pct=risk_pct,
        reward_amount=reward,
        reward_pct=reward_pct,
        timeframe=timeframe,
        indicators=signals,
        summary=summary_en,
        summary_kh=summary_kh,
        key_reasons=key_reasons,
        atr_data=atr_data,
        support_resistance=sr,
        optimal_entry_min=optimal_min,
        optimal_entry_max=optimal_max,
        optimal_entry_target=optimal_target,
        is_optimal_now=is_optimal,
        entry_timing_status=timing_status,
        entry_timing_kh=timing_kh,
        entry_technique=entry_technique,
        market_name=market.name,
        category=market.category,
        emoji=market.emoji,
    )
