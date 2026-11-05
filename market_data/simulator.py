"""Deterministic-seed synthetic market feed for ChronosMatch paper trading."""
from __future__ import annotations
import random
import time
from collections import deque

INSTRUMENTS = {
    "RELIANCE": ("Reliance Industries", 1425.20, "Energy"),
    "TCS": ("Tata Consultancy Services", 3240.50, "IT"),
    "INFY": ("Infosys", 1620.40, "IT"),
    "HDFCBANK": ("HDFC Bank", 985.30, "Banking"),
    "ICICIBANK": ("ICICI Bank", 1288.75, "Banking"),
    "SBIN": ("State Bank of India", 812.40, "Banking"),
    "ITC": ("ITC Limited", 438.60, "FMCG"),
    "LT": ("Larsen & Toubro", 3560.00, "Infrastructure"),
    "BHARTIARTL": ("Bharti Airtel", 1845.25, "Telecom"),
    "TATAMOTORS": ("Tata Motors", 742.10, "Automotive"),
}

class SimulatedMarketData:
    def __init__(self, seed: int = 42, history_size: int = 500):
        self.rng = random.Random(seed)
        self.running = False
        self._quotes = {}
        self._history = {s: deque(maxlen=history_size) for s in INSTRUMENTS}
        self._previous = {}
        for symbol, (name, price, sector) in INSTRUMENTS.items():
            self._quotes[symbol] = {
                "symbol": symbol, "company": name, "sector": sector,
                "price": price, "change": 0.0, "change_pct": 0.0,
                "volume": 0, "timestamp": time.time()
            }
            self._previous[symbol] = price
            self._history[symbol].append(self._bar(symbol, price, 0))

    def _bar(self, symbol, price, volume):
        return {"timestamp": time.time(), "open": price, "high": price,
                "low": price, "close": price, "volume": volume}

    def start(self): self.running = True
    def pause(self): self.running = False
    def reset(self):
        self.__init__()

    def tick(self, steps=1):
        if not self.running:
            return self.snapshot()
        for _ in range(max(1, steps)):
            for symbol, quote in self._quotes.items():
                old = quote["price"]
                move = self.rng.gauss(0, max(old * 0.0007, 0.01))
                new = max(1.0, round(old + move, 2))
                quote["price"] = new
                quote["change"] = round(new - self._previous[symbol], 2)
                quote["change_pct"] = round(
                    (quote["change"] / self._previous[symbol]) * 100, 3
                )
                volume = self.rng.randint(10, 2500)
                quote["volume"] += volume
                quote["timestamp"] = time.time()
                self._history[symbol].append({
                    "timestamp": quote["timestamp"], "open": old,
                    "high": max(old, new), "low": min(old, new),
                    "close": new, "volume": volume
                })
        return self.snapshot()

    def quote(self, symbol): return dict(self._quotes[symbol])
    def quotes(self): return [dict(q) for q in self._quotes.values()]
    def history(self, symbol, limit=120):
        return list(self._history[symbol])[-limit:]
    def snapshot(self): return self.quotes()

    def indices(self):
        # Clearly synthetic index proxies, not official exchange values.
        base = {"NIFTY 50": 26214.60, "SENSEX": 85420.30,
                "BANK NIFTY": 59820.50, "INDIA VIX": 14.25}
        result = []
        for name, value in base.items():
            drift = sum(q["change_pct"] for q in self._quotes.values()) / len(self._quotes)
            scale = -0.12 if name == "INDIA VIX" else 1.0
            result.append({"name": name, "value": round(value * (1 + drift * scale / 100), 2),
                           "change_pct": round(drift * scale, 2)})
        return result
