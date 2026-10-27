
import random
import time
from collections import deque

import pandas as pd
import streamlit as st

from engine.order_book import OrderBook
from ipc.ring_buffer import RingBuffer

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
    dashboard_mode = st.radio(
     "Dashboard Mode",
     ["Direct Engine", "Ring Buffer Pipeline"],
     index=0,
     help="Choose whether orders go directly to Cython or through the memory-mapped ring buffer first.",
)

st.info(
    "Orders are simulated locally. No live exchange feed is connected."
)

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

# Create a ring buffer for this dashboard refresh when pipeline mode is selected
pipeline_buffer = (
    RingBuffer(capacity=128)
    if dashboard_mode == "Ring Buffer Pipeline"
    else None
)

try:
    for _ in range(batch_size):
        st.session_state.order_id += 1

        side = random.choice((1, 2))  # 1 = BUY, 2 = SELL
        price = random.randint(9900, 10100)
        quantity = random.randint(1, 10)

        start = time.perf_counter_ns()

        try:
            if pipeline_buffer is not None:
                # Write the order to the ring buffer
                written = pipeline_buffer.write_order(
                    st.session_state.order_id,
                    side,
                    price,
                    quantity,
                )

                if not written:
                    raise RuntimeError("Ring buffer is full")

                # Read the order and pass it to the Cython engine
                order = pipeline_buffer.read_order()

                if order is None:
                    raise RuntimeError("Ring buffer returned no order")

                book.add_order(*order)

            else:
                # Direct Engine mode
                book.add_order(
                    st.session_state.order_id,
                    side,
                    price,
                    quantity,
                )

            latency_us = (
                time.perf_counter_ns() - start
            ) / 1000

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

finally:
    if pipeline_buffer is not None:
        pipeline_buffer.close()

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



# --- MARKET DEPTH ---
st.markdown("---")
st.subheader("📊 Market Depth")

depth = book.get_market_depth(5)

bid_depth_df = pd.DataFrame(depth["bids"])
ask_depth_df = pd.DataFrame(depth["asks"])

# Format bid prices
if not bid_depth_df.empty:
    bid_depth_df["Price"] = bid_depth_df["price"] / 100
    bid_depth_df = bid_depth_df[["Price", "quantity"]].rename(
        columns={"quantity": "Quantity"}
    )

# Format ask prices
if not ask_depth_df.empty:
    ask_depth_df["Price"] = ask_depth_df["price"] / 100
    ask_depth_df = ask_depth_df[["Price", "quantity"]].rename(
        columns={"quantity": "Quantity"}
    )

bid_col, ask_col = st.columns(2)

with bid_col:
    st.markdown("#### 🟢 BID DEPTH")
    if not bid_depth_df.empty:
        st.dataframe(
            bid_depth_df,
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("No resting buy orders.")

with ask_col:
    st.markdown("#### 🔴 ASK DEPTH")
    if not ask_depth_df.empty:
        st.dataframe(
            ask_depth_df,
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("No resting sell orders.")


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
# ============================================================
# BENCHMARK ANALYTICS
# ============================================================

st.divider()
st.markdown("## BENCHMARK ANALYTICS")
st.caption(
    "Controlled Benchmark V2 results from repeated 100,000-order trials. "
    "These measurements are separate from the live dashboard simulation."
)

from pathlib import Path

benchmark_files = {
    "Repeat 1": Path("benchmark_v2_repeat1.csv"),
    "Repeat 2": Path("benchmark_v2_repeat2.csv"),
}

benchmark_frames = []

for session_name, file_path in benchmark_files.items():
    if file_path.exists():
        try:
            frame = pd.read_csv(file_path)

            required_columns = {
                "mode",
                "orders",
                "throughput_ops",
                "sampled_median_latency_us",
                "sampled_p95_latency_us",
                "sampled_p99_latency_us",
                "avg_write_us",
                "avg_read_us",
                "avg_engine_us",
                "trades",
                "run",
            }

            missing_columns = required_columns - set(frame.columns)

            if missing_columns:
                st.warning(
                    f"{file_path.name} is missing columns: "
                    f"{', '.join(sorted(missing_columns))}"
                )
            else:
                frame["Session"] = session_name
                benchmark_frames.append(frame)

        except Exception as exc:
            st.warning(f"Could not read {file_path.name}: {exc}")
    else:
        st.warning(f"Benchmark file not found: {file_path}")

if benchmark_frames:
    benchmark_df = pd.concat(
        benchmark_frames,
        ignore_index=True,
    )

    # Normalize mode labels for consistent charts.
    benchmark_df["mode"] = (
        benchmark_df["mode"].astype(str).str.lower().str.strip()
    )

    mode_names = {
        "direct": "Direct Engine",
        "pipeline": "Ring Buffer Pipeline",
    }

    benchmark_df["Mode"] = benchmark_df["mode"].map(mode_names)
    benchmark_df = benchmark_df.dropna(subset=["Mode"])

    if not benchmark_df.empty:
        # ----------------------------------------------------
        # OVERALL BENCHMARK SUMMARY
        # ----------------------------------------------------

        summary = (
            benchmark_df.groupby("Mode")
            .agg(
                Trials=("throughput_ops", "count"),
                Orders=("orders", "median"),
                Throughput=("throughput_ops", "median"),
                Median_Latency=("sampled_median_latency_us", "median"),
                P95_Latency=("sampled_p95_latency_us", "median"),
                P99_Latency=("sampled_p99_latency_us", "median"),
                Engine_Time=("avg_engine_us", "median"),
                Write_Time=("avg_write_us", "median"),
                Read_Time=("avg_read_us", "median"),
            )
        )

        direct_row = summary.loc["Direct Engine"] if (
            "Direct Engine" in summary.index
        ) else None

        pipeline_row = summary.loc["Ring Buffer Pipeline"] if (
            "Ring Buffer Pipeline" in summary.index
        ) else None

        # ----------------------------------------------------
        # PERFORMANCE CARDS
        # ----------------------------------------------------

        direct_col, pipeline_col, ratio_col = st.columns(3)

        with direct_col:
            if direct_row is not None:
                st.metric(
                    "DIRECT ENGINE THROUGHPUT",
                    f"{direct_row['Throughput']:,.0f} orders/sec",
                )
                st.caption(
                    f"Median sampled latency: "
                    f"{direct_row['Median_Latency']:.2f} µs"
                )

        with pipeline_col:
            if pipeline_row is not None:
                st.metric(
                    "PIPELINE THROUGHPUT",
                    f"{pipeline_row['Throughput']:,.0f} orders/sec",
                )
                st.caption(
                    f"Median sampled latency: "
                    f"{pipeline_row['Median_Latency']:.2f} µs"
                )

        with ratio_col:
            if direct_row is not None and pipeline_row is not None:
                if pipeline_row["Throughput"] > 0:
                    ratio = (
                        direct_row["Throughput"]
                        / pipeline_row["Throughput"]
                    )
                    st.metric(
                        "DIRECT / PIPELINE",
                        f"{ratio:.2f}x",
                    )
                    st.caption(
                        "Throughput ratio; higher means "
                        "the direct path processed more orders/sec."
                    )

        # ----------------------------------------------------
        # THROUGHPUT COMPARISON
        # ----------------------------------------------------

        st.markdown("### Throughput Comparison")
        st.caption(
            "Each bar represents the median throughput for a session "
            "and mode. Throughput is measured over the full trial."
        )

        throughput_chart = (
            benchmark_df.groupby(["Session", "Mode"])["throughput_ops"]
            .median()
            .unstack("Mode")
        )

        st.bar_chart(
            throughput_chart,
            y_label="Orders per second",
            height=350,
        )

        # ----------------------------------------------------
        # LATENCY COMPARISON
        # ----------------------------------------------------

        st.markdown("### Latency Percentiles")
        st.caption(
            "Median of the sampled latency statistics across trials. "
            "Samples were collected every 100 orders; these are not "
            "percentiles calculated from every order."
        )

        latency_summary = summary[
            ["Median_Latency", "P95_Latency", "P99_Latency"]
        ].rename(
            columns={
                "Median_Latency": "Median (µs)",
                "P95_Latency": "P95 (µs)",
                "P99_Latency": "P99 (µs)",
            }
        )

        st.bar_chart(
            latency_summary,
            y_label="Latency (µs)",
            height=350,
        )

        # ----------------------------------------------------
        # PIPELINE STAGE TIMINGS
        # ----------------------------------------------------

        st.markdown("### Pipeline Stage Timings")
        st.caption(
            "Median sampled time per stage. These are measurements "
            "from the benchmark pipeline, not dashboard refresh timings."
        )

        if pipeline_row is not None:
            stage_data = pd.DataFrame(
                {
                    "Stage": [
                        "Ring Buffer Write",
                        "Ring Buffer Read",
                        "Matching Engine",
                    ],
                    "Latency (µs)": [
                        pipeline_row["Write_Time"],
                        pipeline_row["Read_Time"],
                        pipeline_row["Engine_Time"],
                    ],
                }
            ).set_index("Stage")

            stage_col, stage_info_col = st.columns([2, 1])

            with stage_col:
                st.bar_chart(
                    stage_data,
                    y_label="Latency (µs)",
                    height=300,
                )

            with stage_info_col:
                st.metric(
                    "WRITE",
                    f"{pipeline_row['Write_Time']:.3f} µs",
                )
                st.metric(
                    "READ",
                    f"{pipeline_row['Read_Time']:.3f} µs",
                )
                st.metric(
                    "ENGINE",
                    f"{pipeline_row['Engine_Time']:.3f} µs",
                )

        # ----------------------------------------------------
        # TRIAL-BY-TRIAL RESULTS
        # ----------------------------------------------------

        st.markdown("### Individual Benchmark Trials")

        display_columns = [
            "Session",
            "run",
            "Mode",
            "orders",
            "throughput_ops",
            "sampled_median_latency_us",
            "sampled_p95_latency_us",
            "sampled_p99_latency_us",
            "avg_write_us",
            "avg_read_us",
            "avg_engine_us",
            "trades",
        ]

        display_df = benchmark_df[display_columns].rename(
            columns={
                "run": "Trial",
                "orders": "Orders",
                "throughput_ops": "Throughput (orders/sec)",
                "sampled_median_latency_us": "Median Latency (µs)",
                "sampled_p95_latency_us": "P95 Latency (µs)",
                "sampled_p99_latency_us": "P99 Latency (µs)",
                "avg_write_us": "Write (µs)",
                "avg_read_us": "Read (µs)",
                "avg_engine_us": "Engine (µs)",
                "trades": "Trades",
            }
        )

        st.dataframe(
            display_df.round(3),
            use_container_width=True,
            hide_index=True,
        )

        # Download the combined benchmark results.
        csv_data = benchmark_df.to_csv(index=False).encode("utf-8")

        st.download_button(
            label="Download Combined Benchmark Results",
            data=csv_data,
            file_name="chronosmatch_benchmark_comparison.csv",
            mime="text/csv",
        )

        st.caption(
            "Results are based on the available CSV trials. "
            "They do not represent live exchange performance or "
            "guaranteed production latency."
        )

else:
    st.info(
        "No benchmark results are available yet. "
        "Run Benchmark V2 and ensure benchmark_v2_repeat1.csv "
        "and benchmark_v2_repeat2.csv are in the project directory."
    )
    # Automatically refresh the dashboard.
time.sleep(refresh_seconds)
st.rerun()