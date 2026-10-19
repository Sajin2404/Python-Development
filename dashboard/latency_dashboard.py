
import curses
import random
import time
from collections import deque

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine.order_book import OrderBook

REFRESH_MS = 100
PRICE_MIN = 9900
PRICE_MAX = 10100
BOOK_CAPACITY = 100_000
MAX_EVENTS_BEFORE_RESET = 50_000


def draw_dashboard(stdscr):
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.timeout(REFRESH_MS)

    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_GREEN, -1)
    curses.init_pair(2, curses.COLOR_RED, -1)
    curses.init_pair(3, curses.COLOR_CYAN, -1)
    curses.init_pair(4, curses.COLOR_YELLOW, -1)

    book = OrderBook(capacity=BOOK_CAPACITY)
    latencies_us = deque(maxlen=100)
    order_count = 0
    total_trades = 0
    latest_latency = 0.0
    last_error = ""

    while True:
        key = stdscr.getch()
        if key in (ord("q"), ord("Q")):
            break

        # Generate an order and submit it to the real Cython engine.
        side = random.choice((1, 2))  # 1 = BUY, 2 = SELL
        price = random.randint(PRICE_MIN, PRICE_MAX)
        quantity = random.randint(1, 10)

        start = time.perf_counter_ns()

        try:
            book.add_order(
                order_count + 1,
                side,
                price,
                quantity,
            )
            latest_latency = (
                time.perf_counter_ns() - start
            ) / 1000

            latencies_us.append(latest_latency)
            order_count += 1
            total_trades = len(book.get_trades())
            last_error = ""

        except Exception as exc:
            latest_latency = (
                time.perf_counter_ns() - start
            ) / 1000
            last_error = f"{type(exc).__name__}: {exc}"

        # Reinitialize before fixed-capacity buffers fill up.
        if order_count >= MAX_EVENTS_BEFORE_RESET:
            book = OrderBook(capacity=BOOK_CAPACITY)
            order_count = 0
            total_trades = 0

        best_bid = book.get_best_bid()
        best_ask = book.get_best_ask()

        spread = (
            best_ask - best_bid
            if best_bid is not None and best_ask is not None
            else None
        )

        avg_latency = (
            sum(latencies_us) / len(latencies_us)
            if latencies_us
            else 0.0
        )

        stdscr.erase()
        height, width = stdscr.getmaxyx()

        def put(y, x, text, attr=0):
            if 0 <= y < height and 0 <= x < width:
                stdscr.addnstr(
                    y,
                    x,
                    text,
                    max(0, width - x - 1),
                    attr,
                )

        put(
            0, 2,
            "CHRONOSMATCH | LIVE CYTHON ORDER BOOK",
            curses.color_pair(3) | curses.A_BOLD,
        )
        put(1, 2, "Press Q to quit", curses.A_DIM)
        put(3, 2, "TOP OF ORDER BOOK", curses.A_BOLD)

        put(5, 4, "BEST BID", curses.color_pair(1) | curses.A_BOLD)
        put(5, 30, "BEST ASK", curses.color_pair(2) | curses.A_BOLD)

        put(
            6, 4,
            f"{best_bid / 100:.2f}" if best_bid is not None else "N/A",
            curses.color_pair(1),
        )
        put(
            6, 30,
            f"{best_ask / 100:.2f}" if best_ask is not None else "N/A",
            curses.color_pair(2),
        )

        put(
            8, 2,
            f"Spread: {spread / 100:.2f}"
            if spread is not None else "Spread: N/A",
            curses.color_pair(4) | curses.A_BOLD,
        )

        put(10, 2, "ORDER-PROCESSING LATENCY", curses.A_BOLD)
        put(11, 4, f"Latest: {latest_latency:.2f} us")
        put(12, 4, f"Average (last {len(latencies_us)}): {avg_latency:.2f} us")
        put(13, 4, f"Successful orders: {order_count}")
        put(14, 4, f"Recorded trades: {total_trades}")

        put(
            16, 2,
            "Source: Cython OrderBook; orders are randomly simulated.",
            curses.color_pair(3),
        )

        if last_error:
            put(18, 2, f"Engine error: {last_error}", curses.color_pair(2))

        stdscr.refresh()


if __name__ == "__main__":
    try:
        curses.wrapper(draw_dashboard)
    except KeyboardInterrupt:
        pass
