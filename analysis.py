import pandas as pd
import numpy as np
from typing import Optional, Dict

def compute_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Compute all technical indicators on a DataFrame with OHLCV columns using pure pandas & numpy."""
    if df.empty or len(df) < 20:
        return df

    df = df.copy()
    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    volume = df["Volume"] if "Volume" in df.columns else pd.Series(0, index=df.index)

    # 1. RSI (14) - Wilder's Smoothing
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
    rs = avg_gain / (avg_loss + 1e-9)
    df["RSI"] = 100 - (100 / (1 + rs))

    # 2. MACD (12, 26, 9)
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    df["MACD"] = ema12 - ema26
    df["MACD_signal"] = df["MACD"].ewm(span=9, adjust=False).mean()
    df["MACD_hist"] = df["MACD"] - df["MACD_signal"]

    # 3. EMAs (9, 21, 50, 200)
    df["EMA_9"] = close.ewm(span=9, adjust=False).mean()
    df["EMA_21"] = close.ewm(span=21, adjust=False).mean()
    df["EMA_50"] = close.ewm(span=50, adjust=False).mean()
    df["EMA_200"] = close.ewm(span=200, adjust=False).mean()

    # 4. ATR (14)
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df["ATR"] = tr.ewm(alpha=1/14, adjust=False).mean()

    # 5. Bollinger Bands (20, 2)
    sma20 = close.rolling(20, min_periods=1).mean()
    std20 = close.rolling(20, min_periods=1).std().fillna(0)
    df["BB_middle"] = sma20
    df["BB_upper"] = sma20 + 2 * std20
    df["BB_lower"] = sma20 - 2 * std20

    # 6. Volume SMA
    df["Volume_SMA"] = volume.rolling(20, min_periods=1).mean()

    # 7. ADX (14) & DMI (+DI, -DI)
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    smooth_pdm = pd.Series(plus_dm, index=df.index).ewm(alpha=1/14, adjust=False).mean()
    smooth_mdm = pd.Series(minus_dm, index=df.index).ewm(alpha=1/14, adjust=False).mean()
    
    df["DMP"] = 100 * (smooth_pdm / (df["ATR"] + 1e-9))
    df["DMN"] = 100 * (smooth_mdm / (df["ATR"] + 1e-9))
    dx = 100 * (df["DMP"] - df["DMN"]).abs() / ((df["DMP"] + df["DMN"]) + 1e-9)
    df["ADX"] = dx.ewm(alpha=1/14, adjust=False).mean()

    # 8. Stochastic (14, 3, 3)
    low14 = low.rolling(14, min_periods=1).min()
    high14 = high.rolling(14, min_periods=1).max()
    stoch_k = 100 * (close - low14) / ((high14 - low14) + 1e-9)
    df["STOCH_K"] = stoch_k
    df["STOCH_D"] = stoch_k.rolling(3, min_periods=1).mean()

    # 9. Support & Resistance (20-bar lookback)
    df["Resistance"] = high.rolling(20, min_periods=1).max()
    df["Support"] = low.rolling(20, min_periods=1).min()

    return df


def get_indicator_signals(df: pd.DataFrame) -> Dict[str, dict]:
    """Generate individual buy/sell/neutral signals from each indicator."""
    signals = {}
    if df.empty or len(df) < 20:
        return {"error": "not_enough_data"}

    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else last
    close = last["Close"]

    # --- RSI ---
    rsi = last.get("RSI")
    if rsi is not None and not pd.isna(rsi):
        if rsi < 30:
            signals["RSI"] = {"signal": "BUY", "value": round(rsi, 1), "reason": f"Oversold (RSI={rsi:.1f})"}
        elif rsi > 70:
            signals["RSI"] = {"signal": "SELL", "value": round(rsi, 1), "reason": f"Overbought (RSI={rsi:.1f})"}
        else:
            signals["RSI"] = {"signal": "NEUTRAL", "value": round(rsi, 1), "reason": f"Neutral (RSI={rsi:.1f})"}

    # --- MACD ---
    macd = last.get("MACD")
    macd_signal = last.get("MACD_signal")
    prev_macd = prev.get("MACD")
    prev_macd_signal = prev.get("MACD_signal")
    if all(v is not None and not pd.isna(v) for v in [macd, macd_signal, prev_macd, prev_macd_signal]):
        if prev_macd < prev_macd_signal and macd > macd_signal:
            signals["MACD"] = {"signal": "BUY", "value": round(macd, 4), "reason": "Bullish crossover (MACD > Signal)"}
        elif prev_macd > prev_macd_signal and macd < macd_signal:
            signals["MACD"] = {"signal": "SELL", "value": round(macd, 4), "reason": "Bearish crossover (MACD < Signal)"}
        elif macd > macd_signal:
            signals["MACD"] = {"signal": "BUY", "value": round(macd, 4), "reason": "MACD above Signal line"}
        else:
            signals["MACD"] = {"signal": "SELL", "value": round(macd, 4), "reason": "MACD below Signal line"}

    # --- EMA Crossover ---
    ema9 = last.get("EMA_9")
    ema21 = last.get("EMA_21")
    ema50 = last.get("EMA_50")
    if all(v is not None and not pd.isna(v) for v in [ema9, ema21, ema50]):
        if ema9 > ema21 > ema50:
            signals["EMA"] = {"signal": "BUY", "value": round(ema9, 2), "reason": "EMA 9 > 21 > 50 (Bullish trend)"}
        elif ema9 < ema21 < ema50:
            signals["EMA"] = {"signal": "SELL", "value": round(ema9, 2), "reason": "EMA 9 < 21 < 50 (Bearish trend)"}
        elif ema9 > ema21:
            signals["EMA"] = {"signal": "BUY", "value": round(ema9, 2), "reason": "EMA 9 above 21 (Short-term bullish)"}
        else:
            signals["EMA"] = {"signal": "SELL", "value": round(ema9, 2), "reason": "EMA 9 below 21 (Short-term bearish)"}

    # --- Bollinger Bands ---
    bb_lower = last.get("BB_lower")
    bb_upper = last.get("BB_upper")
    bb_middle = last.get("BB_middle")
    if all(v is not None and not pd.isna(v) for v in [bb_lower, bb_upper, bb_middle]):
        if close <= bb_lower:
            signals["BB"] = {"signal": "BUY", "value": round(close, 2), "reason": "Price touches lower band (oversold)"}
        elif close >= bb_upper:
            signals["BB"] = {"signal": "SELL", "value": round(close, 2), "reason": "Price touches upper band (overbought)"}
        elif close > bb_middle:
            signals["BB"] = {"signal": "BUY", "value": round(close, 2), "reason": "Price above middle band"}
        else:
            signals["BB"] = {"signal": "SELL", "value": round(close, 2), "reason": "Price below middle band"}

    # --- ADX (Trend Strength) ---
    adx = last.get("ADX")
    dmp = last.get("DMP")
    dmn = last.get("DMN")
    if all(v is not None and not pd.isna(v) for v in [adx, dmp, dmn]):
        if adx > 25:
            if dmp > dmn:
                signals["ADX"] = {"signal": "BUY", "value": round(adx, 1), "reason": f"Strong Bullish Trend (ADX={adx:.1f}, +DI > -DI)"}
            else:
                signals["ADX"] = {"signal": "SELL", "value": round(adx, 1), "reason": f"Strong Bearish Trend (ADX={adx:.1f}, -DI > +DI)"}
        else:
            signals["ADX"] = {"signal": "NEUTRAL", "value": round(adx, 1), "reason": f"Range-bound market (ADX={adx:.1f} < 25)"}

    # --- Stochastic ---
    stoch_k = last.get("STOCH_K")
    stoch_d = last.get("STOCH_D")
    if all(v is not None and not pd.isna(v) for v in [stoch_k, stoch_d]):
        if stoch_k < 20 and stoch_d < 20:
            signals["STOCH"] = {"signal": "BUY", "value": round(stoch_k, 1), "reason": f"Oversold (Stoch={stoch_k:.1f})"}
        elif stoch_k > 80 and stoch_d > 80:
            signals["STOCH"] = {"signal": "SELL", "value": round(stoch_k, 1), "reason": f"Overbought (Stoch={stoch_k:.1f})"}
        else:
            signals["STOCH"] = {"signal": "NEUTRAL", "value": round(stoch_k, 1), "reason": f"Neutral (Stoch={stoch_k:.1f})"}

    # --- Volume Confirmation ---
    vol = last.get("Volume")
    vol_sma = last.get("Volume_SMA")
    if vol is not None and vol_sma is not None and not pd.isna(vol_sma) and vol_sma > 0:
        if vol > vol_sma * 1.5:
            signals["VOLUME"] = {"signal": "CONFIRM", "value": round(vol / vol_sma, 1), "reason": f"High Volume ({vol/vol_sma:.1f}x avg)"}
        else:
            signals["VOLUME"] = {"signal": "NEUTRAL", "value": round(vol / vol_sma, 1), "reason": "Average Volume"}

    # --- Macro Trend (EMA 200) ---
    ema200 = last.get("EMA_200")
    if ema200 is not None and not pd.isna(ema200):
        if close > ema200:
            signals["TREND_LONG"] = {"signal": "BUY", "value": round(close, 2), "reason": "Bullish Macro (Price above EMA 200)"}
        else:
            signals["TREND_LONG"] = {"signal": "SELL", "value": round(close, 2), "reason": "Bearish Macro (Price below EMA 200)"}

    return signals


def get_atr_levels(df: pd.DataFrame) -> Optional[dict]:
    """Extract ATR-based Stop Loss and Take Profit levels."""
    if df.empty:
        return None
    last = df.iloc[-1]
    atr = last.get("ATR")
    close = last["Close"]
    if atr is None or pd.isna(atr) or atr == 0:
        return None
    return {
        "ATR": round(atr, 4),
        "SL_1x": round(close - atr, 2),
        "TP_1x": round(close + atr, 2),
        "TP_1_5x": round(close + atr * 1.5, 2),
        "TP_2x": round(close + atr * 2, 2),
        "SL_1_5x": round(close - atr * 1.5, 2),
    }


def get_support_resistance(df: pd.DataFrame) -> dict:
    """Get recent support and resistance levels."""
    if df.empty:
        return {"support": 0, "resistance": 0, "close": 0}
    last = df.iloc[-1]
    return {
        "support": round(float(last.get("Support", last["Low"])), 2),
        "resistance": round(float(last.get("Resistance", last["High"])), 2),
        "close": round(float(last["Close"]), 2),
    }


def compute_full_analysis(df: pd.DataFrame) -> dict:
    """Run full technical analysis and return structured results."""
    df = compute_all_indicators(df)
    signals = get_indicator_signals(df)
    atr = get_atr_levels(df)
    sr = get_support_resistance(df)
    return {
        "signals": signals,
        "atr": atr,
        "support_resistance": sr,
        "last_price": round(float(df.iloc[-1]["Close"]), 4),
        "df": df
    }
