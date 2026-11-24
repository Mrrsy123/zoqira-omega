#!/usr/bin/env python3
"""
Zoqira Web Server — Real-time Market Analysis & Signal Entry Dashboard
Powered by Starlette & Uvicorn
"""

import os
import sys
import json
import asyncio
from datetime import datetime
from typing import Optional, List, Dict
from contextlib import asynccontextmanager

import uvicorn
from starlette.applications import Starlette
from starlette.responses import JSONResponse, FileResponse, HTMLResponse
from starlette.routing import Route, Mount
from starlette.staticfiles import StaticFiles
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware

# Ensure local modules are accessible
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from config import MARKETS, CATEGORIES, TIMEFRAMES
from market_data import fetch_ohlcv, get_current_price, get_multi_prices, normalize_symbol
from analysis import compute_full_analysis
from signals import generate_signal, calculate_lot_size, TradingSignal

# In-memory Auto-Dropped Signals Feed
TRIGGERED_SIGNALS_FEED = []

def send_telegram_alert(sig: TradingSignal):
    """Send real-time alert to Telegram channel or user when PC is off."""
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        return

    msg = (
        f"🎯 *ZOQIRA 24/7 AUTO-SIGNAL DROPPED*\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"📊 {sig.emoji} *{sig.symbol}* ({sig.market_name})\n"
        f"⚡ *សញ្ញា / ACTION:* *{sig.direction}* ({sig.confidence}% confidence)\n\n"
        f"💰 *Entry:* `${sig.entry_price:,.2f}`\n"
        f"🛑 *Stop Loss:* `${sig.stop_loss:,.2f}` (-${sig.risk_amount:,.2f})\n"
        f"🎯 *Take Profit 1:* `${sig.take_profit_1:,.2f}`\n"
        f"🎯 *Take Profit 2:* `${sig.take_profit_2:,.2f}`\n"
        f"🎯 *Take Profit 3:* `${sig.take_profit_3:,.2f}`\n"
        f"⚖️ *Risk/Reward:* 1:{sig.risk_reward}\n\n"
        f"💡 _{sig.entry_timing_kh}_\n"
        f"⏱ ម៉ោង: {datetime.now().strftime('%H:%M:%S')} (GMT+7)"
    )

    try:
        import httpx
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"}
        with httpx.Client(timeout=8) as client:
            client.post(url, json=payload)
    except Exception as e:
        print(f"Telegram alert error: {e}")

def record_optimal_signal(sig: TradingSignal):
    now_str = datetime.now().strftime("%H:%M:%S")
    # Avoid duplicate spam within recent entries
    for item in TRIGGERED_SIGNALS_FEED[:4]:
        if item["symbol"] == sig.symbol and item["direction"] == sig.direction and abs(item["entry_price"] - sig.entry_price) < 1.0:
            return

    TRIGGERED_SIGNALS_FEED.insert(0, {
        "id": len(TRIGGERED_SIGNALS_FEED) + 1,
        "time": now_str,
        "symbol": sig.symbol,
        "emoji": sig.emoji,
        "direction": sig.direction,
        "confidence": sig.confidence,
        "entry_price": sig.entry_price,
        "optimal_target": sig.optimal_entry_target,
        "stop_loss": sig.stop_loss,
        "take_profit": sig.take_profit_2,
        "take_profit_1": sig.take_profit_1,
        "take_profit_3": sig.take_profit_3,
        "risk_reward": sig.risk_reward,
        "technique": sig.entry_technique,
        "status": "🎯 OPTIMAL ENTRY TRIGGERED"
    })
    if len(TRIGGERED_SIGNALS_FEED) > 50:
        TRIGGERED_SIGNALS_FEED.pop()

    # Send telegram broadcast
    send_telegram_alert(sig)

# -------------------- API Handlers --------------------

async def get_markets_api(request):
    """Return all supported markets organized by category."""
    categorized = {}
    for cat, symbols in CATEGORIES.items():
        categorized[cat] = []
        for s in symbols:
            m = MARKETS.get(s)
            if m:
                categorized[cat].append({
                    "symbol": m.symbol,
                    "name": m.name,
                    "category": m.category,
                    "emoji": m.emoji,
                    "yahoo_symbol": m.yahoo_symbol,
                })
    return JSONResponse({
        "status": "success",
        "categories": categorized,
        "total_markets": len(MARKETS),
        "timeframes": TIMEFRAMES,
    })


async def get_prices_api(request):
    """Return live prices for all markets (used for ticker tape)."""
    symbols = list(MARKETS.keys())
    results = get_multi_prices(symbols)
    return JSONResponse({
        "status": "success",
        "count": len(results),
        "timestamp": datetime.utcnow().isoformat(),
        "prices": results,
    })


async def get_analysis_api(request):
    """Return comprehensive analysis and signal entry for a requested symbol and timeframe."""
    symbol = normalize_symbol(request.path_params.get("symbol", "XAUUSD"))
    timeframe = request.query_params.get("timeframe", "1h").lower()

    if symbol not in MARKETS:
        return JSONResponse({"status": "error", "message": f"Symbol '{symbol}' not found"}, status_code=404)

    # 1. Generate Signal
    sig = generate_signal(symbol, timeframe)
    if not sig:
        return JSONResponse({"status": "error", "message": f"Could not fetch data for {symbol}"}, status_code=500)

    # 2. Fetch candles for chart
    tf_map = {
        "15m": ("15m", "5d"),
        "1h": ("1h", "30d"),
        "4h": ("1h", "60d"),
        "1d": ("1d", "90d"),
    }
    interval, period = tf_map.get(timeframe, ("1h", "30d"))
    df = fetch_ohlcv(symbol, interval=interval, period=period)

    candles = []
    overlays = {
        "ema_9": [], "ema_21": [], "ema_50": [], "ema_200": [],
        "bb_upper": [], "bb_middle": [], "bb_lower": [],
        "rsi": [], "macd": [], "macd_signal": [], "macd_hist": [],
    }

    if df is not None and not df.empty:
        full_analysis = compute_full_analysis(df)
        df_ind = full_analysis.get("df", df)

        for idx, row in df_ind.iterrows():
            ts = int(idx.timestamp())
            candles.append({
                "time": ts,
                "open": round(float(row["Open"]), 4),
                "high": round(float(row["High"]), 4),
                "low": round(float(row["Low"]), 4),
                "close": round(float(row["Close"]), 4),
                "volume": round(float(row.get("Volume", 0)), 2),
            })
            if "EMA_9" in row and not row.isna()["EMA_9"]:
                overlays["ema_9"].append({"time": ts, "value": round(float(row["EMA_9"]), 4)})
            if "EMA_21" in row and not row.isna()["EMA_21"]:
                overlays["ema_21"].append({"time": ts, "value": round(float(row["EMA_21"]), 4)})
            if "EMA_50" in row and not row.isna()["EMA_50"]:
                overlays["ema_50"].append({"time": ts, "value": round(float(row["EMA_50"]), 4)})
            if "EMA_200" in row and not row.isna()["EMA_200"]:
                overlays["ema_200"].append({"time": ts, "value": round(float(row["EMA_200"]), 4)})
            if "BB_upper" in row and not row.isna()["BB_upper"]:
                overlays["bb_upper"].append({"time": ts, "value": round(float(row["BB_upper"]), 4)})
            if "BB_middle" in row and not row.isna()["BB_middle"]:
                overlays["bb_middle"].append({"time": ts, "value": round(float(row["BB_middle"]), 4)})
            if "BB_lower" in row and not row.isna()["BB_lower"]:
                overlays["bb_lower"].append({"time": ts, "value": round(float(row["BB_lower"]), 4)})
            if "RSI" in row and not row.isna()["RSI"]:
                overlays["rsi"].append({"time": ts, "value": round(float(row["RSI"]), 2)})
            if "MACD" in row and not row.isna()["MACD"]:
                overlays["macd"].append({"time": ts, "value": round(float(row["MACD"]), 4)})
                overlays["macd_signal"].append({"time": ts, "value": round(float(row.get("MACD_signal", 0)), 4)})
                overlays["macd_hist"].append({"time": ts, "value": round(float(row.get("MACD_hist", 0)), 4)})

    # Default lot calculation on $1000 balance with 2% risk
    lot_info = calculate_lot_size(1000.0, 2.0, sig.entry_price, sig.stop_loss, sig.symbol)

    # Record optimal signal to feed if condition met
    if sig.direction != "NEUTRAL" and sig.is_optimal_now:
        record_optimal_signal(sig)

    return JSONResponse({
        "status": "success",
        "symbol": sig.symbol,
        "name": sig.market_name,
        "emoji": sig.emoji,
        "category": sig.category,
        "timeframe": sig.timeframe,
        "timestamp": datetime.utcnow().isoformat(),
        "signal": {
            "direction": sig.direction,
            "confidence": sig.confidence,
            "entry_price": sig.entry_price,
            "stop_loss": sig.stop_loss,
            "take_profit": sig.take_profit,
            "take_profit_1": sig.take_profit_1,
            "take_profit_2": sig.take_profit_2,
            "take_profit_3": sig.take_profit_3,
            "risk_reward": sig.risk_reward,
            "risk_amount": sig.risk_amount,
            "risk_pct": sig.risk_pct,
            "reward_amount": sig.reward_amount,
            "reward_pct": sig.reward_pct,
            "summary_en": sig.summary,
            "summary_kh": sig.summary_kh,
            "key_reasons": sig.key_reasons,
            "optimal_entry_min": sig.optimal_entry_min,
            "optimal_entry_max": sig.optimal_entry_max,
            "optimal_entry_target": sig.optimal_entry_target,
            "is_optimal_now": sig.is_optimal_now,
            "entry_timing_status": sig.entry_timing_status,
            "entry_timing_kh": sig.entry_timing_kh,
            "entry_technique": sig.entry_technique,
        },
        "indicators": sig.indicators,
        "atr": sig.atr_data,
        "support_resistance": sig.support_resistance,
        "lot_sizing": lot_info,
        "candles": candles,
        "overlays": overlays,
    })


async def get_signals_feed_api(request):
    """Return the live feed of auto-dropped optimal entry signals."""
    return JSONResponse({
        "status": "success",
        "count": len(TRIGGERED_SIGNALS_FEED),
        "feed": TRIGGERED_SIGNALS_FEED
    })


async def get_confluence_api(request):
    """Analyze all 4 timeframes (15m, 1h, 4h, 1d) for confluence alignment."""
    symbol = normalize_symbol(request.path_params.get("symbol", "XAUUSD"))
    if symbol not in MARKETS:
        return JSONResponse({"status": "error", "message": "Symbol not found"}, status_code=404)

    tf_results = {}
    timeframes = ["15m", "1h", "4h", "1d"]
    agree_count = 0
    directions = []

    for tf in timeframes:
        sig = generate_signal(symbol, tf)
        if sig:
            tf_results[tf] = {
                "direction": sig.direction,
                "confidence": sig.confidence,
                "entry_price": sig.entry_price,
                "rsi": sig.indicators.get("RSI", {}).get("value", 50),
                "trend": sig.indicators.get("ADX", {}).get("signal", "NEUTRAL"),
            }
            if sig.direction != "NEUTRAL":
                directions.append(sig.direction)

    # Determine overall confluence
    buy_count = directions.count("BUY")
    sell_count = directions.count("SELL")

    if buy_count >= 3:
        overall = "STRONG_BUY"
        confluence_score = round((buy_count / 4) * 100)
    elif buy_count == 2 and sell_count == 0:
        overall = "MODERATE_BUY"
        confluence_score = 65
    elif sell_count >= 3:
        overall = "STRONG_SELL"
        confluence_score = round((sell_count / 4) * 100)
    elif sell_count == 2 and buy_count == 0:
        overall = "MODERATE_SELL"
        confluence_score = 65
    else:
        overall = "MIXED_NEUTRAL"
        confluence_score = 40

    return JSONResponse({
        "status": "success",
        "symbol": symbol,
        "overall_bias": overall,
        "confluence_score": confluence_score,
        "timeframes": tf_results,
    })


async def get_scan_api(request):
    """Quick scan of all markets to rank top opportunities."""
    opportunities = []
    for sym in MARKETS.keys():
        try:
            sig = generate_signal(sym, "1h")
            if sig:
                opportunities.append({
                    "symbol": sig.symbol,
                    "name": sig.market_name,
                    "emoji": sig.emoji,
                    "category": sig.category,
                    "direction": sig.direction,
                    "confidence": sig.confidence,
                    "entry_price": sig.entry_price,
                    "stop_loss": sig.stop_loss,
                    "take_profit": sig.take_profit,
                    "risk_reward": sig.risk_reward,
                    "risk_pct": sig.risk_pct,
                    "reward_pct": sig.reward_pct,
                })
        except Exception:
            continue

    # Sort opportunities: high confidence first, exclude neutrals or put them at bottom
    ranked = sorted(opportunities, key=lambda x: (x["direction"] != "NEUTRAL", x["confidence"]), reverse=True)

    return JSONResponse({
        "status": "success",
        "count": len(ranked),
        "timestamp": datetime.utcnow().isoformat(),
        "opportunities": ranked,
    })


async def post_calculate_lot_api(request):
    """Calculate customized lot size given balance and risk percentage."""
    try:
        body = await request.json()
        balance = float(body.get("balance", 1000.0))
        risk_pct = float(body.get("risk_pct", 2.0))
        entry = float(body.get("entry", 0.0))
        sl = float(body.get("sl", 0.0))
        symbol = str(body.get("symbol", "XAUUSD"))

        res = calculate_lot_size(balance, risk_pct, entry, sl, symbol)
        return JSONResponse({"status": "success", "data": res})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=400)


async def serve_index(request):
    """Serve main single-page web app."""
    index_path = os.path.join(CURRENT_DIR, "static", "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return HTMLResponse("<h1>Zoqira Web Dashboard</h1><p>static/index.html not found.</p>")


# -------------------- App Routes --------------------

routes = [
    Route("/", serve_index),
    Route("/api/markets", get_markets_api),
    Route("/api/prices", get_prices_api),
    Route("/api/analysis/{symbol}", get_analysis_api),
    Route("/api/confluence/{symbol}", get_confluence_api),
    Route("/api/scan", get_scan_api),
    Route("/api/signals_feed", get_signals_feed_api),
    Route("/api/calculate_lot", post_calculate_lot_api, methods=["POST"]),
    Mount("/static", StaticFiles(directory=os.path.join(CURRENT_DIR, "static")), name="static"),
]

middleware = [
    Middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]),
]

async def background_market_monitor():
    """Autonomous 24/7 background monitor for XAUUSD and BTCUSD on cloud."""
    print("🚀 24/7 Background Market Monitor active on Cloud...")
    await asyncio.sleep(10)
    while True:
        try:
            for sym in ["XAUUSD", "BTCUSD"]:
                sig = generate_signal(sym, "1h")
                if sig and sig.direction != "NEUTRAL" and sig.is_optimal_now:
                    record_optimal_signal(sig)
                await asyncio.sleep(4)
        except Exception as e:
            print(f"Background monitor error: {e}")
        await asyncio.sleep(60)

@asynccontextmanager
async def lifespan(app):
    task = asyncio.create_task(background_market_monitor())
    yield
    task.cancel()

app = Starlette(debug=True, routes=routes, middleware=middleware, lifespan=lifespan)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"\n{'='*60}")
    print(f"🚀 ZOQIRA TRADING WEB DASHBOARD")
    print(f"📡 Server running at: http://localhost:{port}")
    print(f"{'='*60}\n")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
