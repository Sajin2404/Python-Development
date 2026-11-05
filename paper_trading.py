"""Paper-trading account that routes orders through the Cython OrderBook."""
from __future__ import annotations
import time
from collections import defaultdict
from engine.order_book import OrderBook
from ipc.ring_buffer import RingBuffer

BUY, SELL = 1, 2

class PaperTradingEngine:
    def __init__(self, starting_cash=1_000_000.0, book_capacity=10000):
        self.starting_cash = float(starting_cash)
        self.cash = float(starting_cash)
        self.reserved_cash = 0.0
        self.reserved_shares = defaultdict(int)
        self.holdings = defaultdict(int)
        self.average_cost = defaultdict(float)
        self.realized_pnl = 0.0
        self.books = {}
        self.orders_by_id = {}
        self.order_sequence = 0
        self.trade_log = []
        self.rejections = []
        self.route_latencies_us = []
        self.book_capacity = book_capacity
        self.seed_order_ids = set()
        self.ring_writes = 0
        self.ring_reads = 0

    def ensure_instrument(self, symbol, reference_price):
        if symbol in self.books:
            return
        book = OrderBook(capacity=self.book_capacity)
        mid = int(round(reference_price * 100))
        spread = max(1, int(round(mid * 0.001)))
        # Explicitly synthetic market-maker liquidity.
        bid_id, ask_id = 9_000_000_000_000_001 + len(self.books) * 2, 9_000_000_000_000_002 + len(self.books) * 2
        book.add_order(bid_id, BUY, max(1, mid - spread), 100000)
        book.add_order(ask_id, SELL, mid + spread, 100000)
        self.seed_order_ids.update((bid_id, ask_id))
        self.books[symbol] = book

    def place_limit_order(self, symbol, side, quantity, limit_price, reference_price):
        started = time.perf_counter_ns()
        side = str(side).upper()
        quantity = int(quantity)
        limit_price = round(float(limit_price), 2)
        if side not in ("BUY", "SELL"):
            raise ValueError("Side must be BUY or SELL")
        if quantity <= 0 or limit_price <= 0:
            raise ValueError("Quantity and limit price must be positive")
        self.ensure_instrument(symbol, reference_price)
        notional = quantity * limit_price
        if side == "BUY" and notional > self.cash:
            return self._reject(symbol, side, quantity, limit_price, "Insufficient available cash")
        if side == "SELL" and quantity > self.holdings[symbol] - self.reserved_shares[symbol]:
            return self._reject(symbol, side, quantity, limit_price, "Insufficient available shares")

        self.order_sequence += 1
        oid = self.order_sequence
        record = {
            "order_id": oid, "symbol": symbol, "side": side,
            "quantity": quantity, "filled_quantity": 0,
            "remaining_quantity": quantity, "limit_price": limit_price,
            "average_fill_price": 0.0, "status": "OPEN",
            "owner": "PAPER_USER", "created_at": time.time(),
            "message": ""
        }
        if side == "BUY":
            self.cash -= notional
            self.reserved_cash += notional
            record["reserved_cash"] = notional
        else:
            self.reserved_shares[symbol] += quantity
            record["reserved_shares"] = quantity
        self.orders_by_id[oid] = record

        before = len(self.books[symbol].get_trades())
        # The actual user order traverses the mmap FIFO before Cython matching.
        with RingBuffer(capacity=4) as buffer:
            if not buffer.write_order(
                oid, BUY if side == "BUY" else SELL,
                int(round(limit_price * 100)), quantity
            ):
                raise RuntimeError("RingBuffer is full")
            self.ring_writes += 1
            payload = buffer.read_order()
            if payload is None:
                raise RuntimeError("RingBuffer returned no order")
            self.ring_reads += 1
        remaining = self.books[symbol].add_order(*payload)
        self._apply_new_trades(symbol, before)
        record["remaining_quantity"] = int(remaining)
        if remaining == 0:
            record["status"] = "FILLED"
        self.route_latencies_us.append((time.perf_counter_ns() - started) / 1000)
        return dict(record)

    def _reject(self, symbol, side, quantity, price, reason):
        row = {"order_id": None, "symbol": symbol, "side": side,
               "quantity": quantity, "filled_quantity": 0,
               "remaining_quantity": quantity, "limit_price": price,
               "average_fill_price": 0.0, "status": "REJECTED",
               "owner": "PAPER_USER", "created_at": time.time(), "message": reason}
        self.rejections.append(row)
        return dict(row)

    def _apply_new_trades(self, symbol, previous_count):
        book = self.books[symbol]
        for trade in book.get_trades()[previous_count:]:
            buy_id, sell_id = trade["buy_order_id"], trade["sell_order_id"]
            price, qty = trade["price"] / 100.0, int(trade["quantity"])
            row = {"symbol": symbol, "buy_order_id": buy_id,
                   "sell_order_id": sell_id, "price": price,
                   "quantity": qty, "value": round(price * qty, 2),
                   "timestamp": time.time(),
                   "buyer": "PAPER_USER" if buy_id in self.orders_by_id else "SIMULATED_LIQUIDITY",
                   "seller": "PAPER_USER" if sell_id in self.orders_by_id else "SIMULATED_LIQUIDITY"}
            self.trade_log.append(row)
            if buy_id in self.orders_by_id:
                order = self.orders_by_id[buy_id]
                self._apply_buy_fill(order, price, qty)
            if sell_id in self.orders_by_id:
                order = self.orders_by_id[sell_id]
                self._apply_sell_fill(order, price, qty)

    def _apply_buy_fill(self, order, price, qty):
        old_qty = self.holdings[order["symbol"]]
        old_cost = self.average_cost[order["symbol"]] * old_qty
        self.holdings[order["symbol"]] += qty
        self.average_cost[order["symbol"]] = (old_cost + price * qty) / (old_qty + qty)
        reserve_release = order["limit_price"] * qty
        self.reserved_cash -= reserve_release
        order["reserved_cash"] -= reserve_release
        self.cash += reserve_release - price * qty
        self._record_fill(order, price, qty)

    def _apply_sell_fill(self, order, price, qty):
        symbol = order["symbol"]
        self.reserved_shares[symbol] -= qty
        order["reserved_shares"] -= qty
        self.realized_pnl += (price - self.average_cost[symbol]) * qty
        self.holdings[symbol] -= qty
        self.cash += price * qty
        if self.holdings[symbol] == 0:
            self.average_cost[symbol] = 0.0
        self._record_fill(order, price, qty)

    def _record_fill(self, order, price, qty):
        old_value = order["average_fill_price"] * order["filled_quantity"]
        order["filled_quantity"] += qty
        order["average_fill_price"] = (old_value + price * qty) / order["filled_quantity"]
        order["remaining_quantity"] = order["quantity"] - order["filled_quantity"]
        order["status"] = "FILLED" if order["remaining_quantity"] == 0 else "PARTIAL"

    def cancel_order(self, order_id):
        order = self.orders_by_id.get(int(order_id))
        if not order or order["status"] not in ("OPEN", "PARTIAL"):
            return False
        book = self.books[order["symbol"]]
        if not book.cancel_order(int(order_id)):
            return False
        remaining = order["remaining_quantity"]
        if order["side"] == "BUY":
            refund = order["limit_price"] * remaining
            self.reserved_cash -= refund
            order["reserved_cash"] -= refund
            self.cash += refund
        else:
            self.reserved_shares[order["symbol"]] -= remaining
            order["reserved_shares"] -= remaining
        order["status"] = "CANCELLED"
        order["message"] = "Cancelled by paper user"
        return True

    def order_book(self, symbol, levels=10, reference_price=None):
        self.ensure_instrument(symbol, reference_price if reference_price is not None else 100.0)
        return self.books[symbol].get_market_depth(levels)

    def orders(self, limit=100):
        return [dict(o) for o in sorted(self.orders_by_id.values(),
                key=lambda x: x["created_at"], reverse=True)[:limit]] + self.rejections

    def trades(self, limit=100):
        return list(reversed(self.trade_log[-limit:]))

    def portfolio(self, marks):
        positions = []
        market_value = 0.0
        unrealized = 0.0
        for symbol, qty in self.holdings.items():
            if qty <= 0:
                continue
            mark = float(marks.get(symbol, self.average_cost[symbol]))
            value = qty * mark
            pnl = (mark - self.average_cost[symbol]) * qty
            market_value += value
            unrealized += pnl
            positions.append({"symbol": symbol, "quantity": qty,
                              "average_cost": self.average_cost[symbol],
                              "last_price": mark, "market_value": value,
                              "unrealized_pnl": pnl})
        return {"cash": self.cash, "market_value": market_value,
                "equity": self.cash + market_value + self.reserved_cash,
                "unrealized_pnl": unrealized, "realized_pnl": self.realized_pnl,
                "total_pnl": unrealized + self.realized_pnl, "positions": positions}

    def metrics(self):
        orders = list(self.orders_by_id.values()) + self.rejections
        return {
            "orders": len(orders),
            "executions": len(self.trade_log),
            "open_orders": sum(o["status"] in ("OPEN", "PARTIAL") for o in orders),
            "rejected": len(self.rejections),
            "cancelled": sum(o["status"] == "CANCELLED" for o in orders),
            "route_latencies_us": list(self.route_latencies_us),
            "ring_writes": self.ring_writes,
            "ring_reads": self.ring_reads,
        }
