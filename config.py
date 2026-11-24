import os
from dataclasses import dataclass
from typing import Dict

# -------------------- Market Definitions --------------------
@dataclass
class Market:
    symbol: str
    yahoo_symbol: str
    category: str
    name: str
    emoji: str

# Only XAUUSD (Gold) and BTCUSD (Bitcoin)
MARKETS: Dict[str, Market] = {
    "XAUUSD": Market("XAUUSD", "GC=F", "Gold", "Gold / US Dollar", "🥇"),
    "BTCUSD": Market("BTCUSD", "BTC-USD", "Crypto", "Bitcoin / US Dollar", "₿"),
}

CATEGORIES = {
    "Primary Markets": ["XAUUSD", "BTCUSD"],
}

TIMEFRAMES = {
    "15m": {"interval": "15m", "period": "5d", "name": "15 Minutes"},
    "1h": {"interval": "1h", "period": "30d", "name": "1 Hour"},
    "4h": {"interval": "1h", "period": "60d", "name": "4 Hours (resampled)"},
    "1d": {"interval": "1d", "period": "90d", "name": "1 Day"},
}

# Bot commands
COMMANDS = [
    ("start", "🚀 ចាប់ផ្តើម / Main Menu"),
    ("signal", "🤖 សញ្ញា AI / AI Signal (XAUUSD / BTCUSD)"),
    ("price", "💹 តម្លៃផ្សាយផ្ទាល់ / Live Price"),
    ("analysis", "🔍 វិភាគបច្ចេកទេស / Technical Analysis"),
    ("trackrecord", "📋 កំណត់ត្រាឈ្នះ-ចាញ់ / Track Record"),
    ("risk", "⚖️ គណនា Risk/Reward / Risk Calculator"),
    ("help", "❓ ជំនួយ / Help"),
]

# Trading terms in Khmer
KH_SIGNAL = {
    "BUY": "ទិញ ⬆️",
    "SELL": "លក់ ⬇️",
    "NEUTRAL": "រង់ចាំ ⏸️",
    "STRONG": "ខ្លាំង 💪",
    "MODERATE": "មធ្យម",
    "WEAK": "ខ្សោយ",
}
