import yfinance as yf
import pandas as pd
from typing import Optional, Dict
from config import MARKETS, Market


def normalize_symbol(symbol_name: str) -> str:
    """Normalize symbol to either XAUUSD or BTCUSD."""
    s = symbol_name.upper().strip()
    if s in ("BTCUSDT", "BTC-USD", "BTC"):
        return "BTCUSD"
    if s in ("GOLD", "XAU", "GC=F"):
        return "XAUUSD"
    return s


def fetch_ohlcv(symbol_name: str, interval: str = "1h", period: str = "30d") -> Optional[pd.DataFrame]:
    """Fetch OHLCV data for XAUUSD or BTCUSD."""
    sym = normalize_symbol(symbol_name)
    market = MARKETS.get(sym)
    if not market:
        return None
    try:
        ticker = yf.Ticker(market.yahoo_symbol)
        df = ticker.history(period=period, interval=interval, auto_adjust=True, prepost=False)
        if df.empty:
            return None
        df.index = pd.to_datetime(df.index)
        return df
    except Exception:
        return None


def get_current_price(symbol_name: str) -> Optional[Dict]:
    """Get current price and daily change for XAUUSD or BTCUSD."""
    sym = normalize_symbol(symbol_name)
    market = MARKETS.get(sym)
    if not market:
        return None
    try:
        ticker = yf.Ticker(market.yahoo_symbol)
        info = ticker.fast_info
        price = info.get("last_price") or info.get("regular_market_previous_close")
        if not price:
            hist = ticker.history(period="2d", interval="1d", auto_adjust=True)
            if len(hist) >= 2:
                price = hist["Close"].iloc[-1]
                prev_close = hist["Close"].iloc[-2]
            elif len(hist) == 1:
                price = hist["Close"].iloc[-1]
                prev_close = price
            else:
                return None
        else:
            prev_close = info.get("previous_close") or price
        change = price - prev_close
        change_pct = (change / prev_close) * 100 if prev_close else 0
        return {
            "symbol": sym,
            "name": market.name,
            "price": price,
            "prev_close": prev_close,
            "change": change,
            "change_pct": change_pct,
            "category": market.category,
            "emoji": market.emoji,
        }
    except Exception:
        return None


def get_multi_prices(symbols: list[str]) -> list[Dict]:
    """Get prices for XAUUSD and BTCUSD."""
    results = []
    yahoo_symbols = []
    symbol_map = {}
    for s in symbols:
        norm = normalize_symbol(s)
        market = MARKETS.get(norm)
        if market and market.yahoo_symbol not in symbol_map:
            yahoo_symbols.append(market.yahoo_symbol)
            symbol_map[market.yahoo_symbol] = norm

    if not yahoo_symbols:
        return []

    try:
        tickers = yf.Tickers(" ".join(yahoo_symbols))
        for ysym, sname in symbol_map.items():
            market = MARKETS[sname]
            try:
                t = tickers.tickers.get(ysym)
                if not t:
                    continue
                info = t.fast_info
                price = info.get("last_price") or info.get("regular_market_previous_close")
                prev_close = info.get("previous_close") or info.get("regular_market_previous_close")
                if not price:
                    hist = t.history(period="5d", interval="1d", auto_adjust=True)
                    if not hist.empty:
                        price = float(hist["Close"].iloc[-1])
                        prev_close = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else price
                if price:
                    if not prev_close:
                        prev_close = price
                    change = price - prev_close
                    change_pct = (change / prev_close) * 100 if prev_close else 0
                    results.append({
                        "symbol": sname,
                        "emoji": market.emoji,
                        "price": price,
                        "change_pct": change_pct,
                    })
            except Exception:
                continue
    except Exception:
        return []
    return results


def get_live_ticker_text(symbol_name: str) -> Optional[str]:
    """Format a price message for XAUUSD or BTCUSD."""
    sym = normalize_symbol(symbol_name)
    data = get_current_price(sym)
    if not data:
        return None
    direction = "🟢" if data["change"] >= 0 else "🔴"
    arrow = "📈" if data["change"] >= 0 else "📉"
    return (
        f"{data['emoji']} *{data['symbol']}* — {data['name']}\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"💰 តម្លៃ: *${data['price']:,.2f}*\n"
        f"{direction} បម្លាស់ប្តូរ: {data['change']:+,.2f} ({data['change_pct']:+,.2f}%)\n"
        f"📊 ថ្ងៃមុនបិទ: ${data['prev_close']:,.2f}\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"🏷️ ប្រភេទ: {data['category']} {arrow}"
    )
