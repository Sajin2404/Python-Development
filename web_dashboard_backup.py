
import random
import time
from collections import deque

import pandas as pd
import streamlit as st

from engine.order_book import OrderBook


st.set_page_config(
    page_title="ChronosMatch",
    page_icon="⚡",
    layout="wide",
)

st.title("⚡ ChronosMatch")
st.subheader("High-Performance Order Matching Dashboard")
st.caption("Cython matching engine · Simulated market data")

# Dashboard settings
with st.sidebar:
    st.header("Settings")
    refresh_seconds = st.slider(
        "Refresh interval (seconds)",
        min_value=1,
        max_value=5,
        value=1,
    )
    max_samples = st.slider(
        "Latency samples",
        min_value=50,
        max_value=500,
        value=100,
        step=50,
    )
    st.info("Orders are simulated locally. No live exchange feed is connected.")

# Keep the order book and measurements between Streamlit reruns.
if "book" not in st.session_state:
    st.session_state.book = OrderBook(capacity=100_000)
    st.session_state.order_id = 0
    st.session_state.successful_orders = 0
    st.session_state.latencies = deque(maxlen=500)
    st.session_state.latency_history = deque(maxlen=500)
    st.session_state.trade_count = 0

# Generate a small batch of simulated orders per refresh.
book = st.session_state.book

if st.session_state.successful_orders >= 50_000:
    st.session_state.book = OrderBook(capacity=100_000)
    st.session_state.order_id = 0
    st.session_state.successful_orders = 0
    st.session_state.trade_count = 0
    st.session_state.latencies.clear()
    st.session_state.latency_history.clear()
    book = st.session_state.book

batch_size = 10

for _ in range(batch_size):
    st.session_state.order_id += 1

    side = random.choice((1, 2))  # 1 = BUY, 2 = SELL
    price = random.randint(9900, 10100)
    quantity = random.randint(1, 10)

    start = time.perf_counter_ns()

    try:
        book.add_order(
            st.session_state.order_id,
            side,
            price,
            quantity,
        )
        latency_us = (time.perf_counter_ns() - start) / 1000

        st.session_state.latencies.append(latency_us)
        st.session_state.latency_history.append(
            {
                "Order": st.session_state.successful_orders + 1,
                "Latency (µs)": latency_us,
            }
        )
        st.session_state.successful_orders += 1

    except Exception as exc:
        st.error(f"Matching engine error: {exc}")
        break

trades = book.get_trades()
st.session_state.trade_count = len(trades)

best_bid = book.get_best_bid()
best_ask = book.get_best_ask()

spread = (
    (best_ask - best_bid) / 100
    if best_bid is not None and best_ask is not None
    else None
)

latencies = list(st.session_state.latencies)

avg_latency = sum(latencies) / len(latencies) if latencies else 0
median_latency = (
    float(pd.Series(latencies).median()) if latencies else 0
)
p95_latency = (
    float(pd.Series(latencies).quantile(0.95)) if latencies else 0
)
p99_latency = (
    float(pd.Series(latencies).quantile(0.99)) if latencies else 0
)

# Main metrics
col1, col2, col3, col4 = st.columns(4)

col1.metric(
    "Best Bid",
    f"{best_bid / 100:.2f}" if best_bid is not None else "N/A",
)
col2.metric(
    "Best Ask",
    f"{best_ask / 100:.2f}" if best_ask is not None else "N/A",
)
col3.metric(
    "Bid–Ask Spread",
    f"{spread:.2f}" if spread is not None else "N/A",
)
col4.metric("Executed Trades", st.session_state.trade_count)

st.divider()
st.subheader("Order-Processing Latency")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Average", f"{avg_latency:.2f} µs")
c2.metric("Median", f"{median_latency:.2f} µs")
c3.metric("P95", f"{p95_latency:.2f} µs")
c4.metric("P99", f"{p99_latency:.2f} µs")

st.caption(
    f"Successfully submitted orders: "
    f"{st.session_state.successful_orders:,}"
)

# Latency chart
history = pd.DataFrame(list(st.session_state.latency_history))

if not history.empty:
    st.subheader("Recent Order Latency")
    st.line_chart(
        history.set_index("Order")["Latency (µs)"],
        height=300,
    )

# Recent executed trades
st.subheader("Recent Executed Trades")

if trades:
    recent_trades = pd.DataFrame(trades[-10:][::-1])
    st.dataframe(recent_trades, use_container_width=True, hide_index=True)
else:
    st.info("Waiting for matching orders to generate trades.")

st.caption(
    "Performance values measure the local add_order() call only. "
    "They are not end-to-end exchange latency measurements."
)

# Automatically refresh the dashboard.
time.sleep(refresh_seconds)
st.rerun()
