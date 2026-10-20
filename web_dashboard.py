
import random
import time
from collections import deque

import pandas as pd
import streamlit as st

from engine.order_book import OrderBook


st.set_page_config(
    page_title="ChronosMatch | Trading Engine",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    .stApp {
        background-color: #0B1220;
        color: #F1F5F9;
    }

    [data-testid="stSidebar"] {
        background-color: #111827;
    }

    [data-testid="stMetric"] {
        background-color: #172338;
        border: 1px solid #263449;
        padding: 18px;
        border-radius: 12px;
    }

    [data-testid="stMetricLabel"] {
        color: #94A3B8;
    }

    [data-testid="stMetricValue"] {
        color: #F8FAFC;
    }

    h1, h2, h3 {
        color: #F8FAFC;
    }

    div[data-testid="stDataFrame"] {
        border: 1px solid #263449;
        border-radius: 10px;
    }

    hr {
        border-color: #263449;
    }
</style>
""", unsafe_allow_html=True)


# Professional trading-terminal header
header_left, header_right = st.columns([4, 1])

with header_left:
    st.markdown(
        """
        <h1 style="margin-bottom:0; color:#F8FAFC;">
            ⚡ CHRONOSMATCH
        </h1>
        <p style="color:#94A3B8; margin-top:4px;">
            ZERO-COPY HIGH-FREQUENCY TRADING ENGINE
        </p>
        """,
        unsafe_allow_html=True,
    )

with header_right:
    st.markdown(
        """
        <div style="
            background:#14251F;
            color:#4ADE80;
            padding:10px;
            border:1px solid #166534;
            border-radius:8px;
            text-align:center;
            font-weight:bold;
            margin-top:12px;
        ">
            SIMULATION
        </div>
        """,
        unsafe_allow_html=True,
    )

st.divider()


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
# Track throughput across dashboard refreshes
if "throughput_samples" not in st.session_state:
    st.session_state.throughput_samples = deque(maxlen=60)

if "last_throughput_time" not in st.session_state:
    st.session_state.last_throughput_time = time.perf_counter()

if "last_throughput_count" not in st.session_state:
    st.session_state.last_throughput_count = 0
    
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
# Calculate observed order throughput
now = time.perf_counter()
elapsed = now - st.session_state.last_throughput_time

if elapsed > 0:
    processed = (
        st.session_state.successful_orders
        - st.session_state.last_throughput_count
    )
    throughput = processed / elapsed
    st.session_state.throughput_samples.append(throughput)

    st.session_state.last_throughput_time = now
    st.session_state.last_throughput_count = (
        st.session_state.successful_orders
    )

current_throughput = (
    st.session_state.throughput_samples[-1]
    if st.session_state.throughput_samples
    else 0.0
)
# Main metrics
# Main market metrics
st.markdown("### MARKET OVERVIEW")

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.markdown(
        '<p style="color:#4ADE80; margin-bottom:0;">BEST BID</p>',
        unsafe_allow_html=True,
    )
    st.metric(
        label="",
        value=f"{best_bid / 100:.2f}" if best_bid is not None else "N/A",
    )

with col2:
    st.markdown(
        '<p style="color:#FB7185; margin-bottom:0;">BEST ASK</p>',
        unsafe_allow_html=True,
    )
    st.metric(
        label="",
        value=f"{best_ask / 100:.2f}" if best_ask is not None else "N/A",
    )

with col3:
    st.markdown(
        '<p style="color:#FACC15; margin-bottom:0;">BID–ASK SPREAD</p>',
        unsafe_allow_html=True,
    )
    st.metric(
        label="",
        value=f"{spread:.2f}" if spread is not None else "N/A",
    )

with col4:
    st.markdown(
        '<p style="color:#60A5FA; margin-bottom:0;">EXECUTED TRADES</p>',
        unsafe_allow_html=True,
    )
    st.metric(
        label="",
        value=f"{st.session_state.trade_count:,}",
    )


st.divider()

st.markdown("### ENGINE PERFORMANCE")
st.caption("Order-processing latency · Microseconds (µs)")

c1, c2, c3, c4, c5, c6 = st.columns(6)

with c1:
    st.metric("AVERAGE", f"{avg_latency:.2f} µs")

with c2:
    st.metric("MEDIAN", f"{median_latency:.2f} µs")

with c3:
    st.metric("P95", f"{p95_latency:.2f} µs")

with c4:
    st.metric("P99", f"{p99_latency:.2f} µs")

with c5:
    max_latency = max(latencies) if latencies else 0.0
    st.metric("MAXIMUM", f"{max_latency:.2f} µs")

with c6:
    st.metric("ORDERS / SEC", f"{current_throughput:,.1f}")
    
st.caption(
    f"Successfully processed orders: "
    f"{st.session_state.successful_orders:,}"
)


# Latency monitoring chart
history = pd.DataFrame(list(st.session_state.latency_history))

st.divider()
st.markdown("### LATENCY MONITOR")
st.caption("Recent order-processing times · Microseconds (µs)")

if not history.empty:
    history = history.tail(max_samples)

    chart_col, stats_col = st.columns([3, 1])

    with chart_col:
        st.line_chart(
            history.set_index("Order")["Latency (µs)"],
            height=350,
        )

    with stats_col:
        recent = history["Latency (µs)"]

        st.metric("RECENT MIN", f"{recent.min():.2f} µs")
        st.metric("RECENT AVG", f"{recent.mean():.2f} µs")
        st.metric("RECENT MAX", f"{recent.max():.2f} µs")

        st.markdown(
            """
            <div style="
                background:#14251F;
                border:1px solid #166534;
                border-radius:8px;
                padding:12px;
                color:#86EFAC;
                font-size:13px;
            ">
                Measurements are collected from local
                Cython engine calls.
            </div>
            """,
            unsafe_allow_html=True,
        )
else:
    st.info("Waiting for latency samples...")

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
