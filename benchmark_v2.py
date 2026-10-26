import argparse
import csv
import random
import statistics
import time

from engine.order_book import OrderBook
from ipc.ring_buffer import RingBuffer


CSV_FILE = "benchmark_v2_results.csv"
LATENCY_SAMPLE_INTERVAL = 100


def percentile(values, percent):
    """Calculate the nearest-rank percentile."""
    if not values:
        return 0.0

    ordered = sorted(values)
    rank = max(1, (percent * len(ordered) + 99) // 100)
    return ordered[min(rank - 1, len(ordered) - 1)]


def generate_orders(count, seed):
    """Generate a repeatable workload outside the timed section."""
    rng = random.Random(seed)

    return [
        (
            order_id,
            rng.choice((1, 2)),
            rng.randint(9900, 10100),
            rng.randint(1, 10),
        )
        for order_id in range(1, count + 1)
    ]


def run_once(mode, orders):
    """Benchmark one mode with sampled latency measurements."""
    book = OrderBook(capacity=len(orders) + 10)

    buffer = (
        RingBuffer(capacity=len(orders) + 10)
        if mode == "pipeline"
        else None
    )

    sampled_latencies_us = []
    write_times_us = []
    read_times_us = []
    engine_times_us = []

    try:
        # Only the loop is included in end-to-end elapsed time.
        total_start = time.perf_counter()

        for index, (order_id, side, price, quantity) in enumerate(orders):
            sample_latency = (
                index % LATENCY_SAMPLE_INTERVAL == 0
            )

            if sample_latency:
                order_start_ns = time.perf_counter_ns()

            if buffer is not None:
                if sample_latency:
                    stage_start_ns = time.perf_counter_ns()

                written = buffer.write_order(
                    order_id, side, price, quantity
                )

                if sample_latency:
                    write_times_us.append(
                        (time.perf_counter_ns() - stage_start_ns) / 1000
                    )

                if not written:
                    raise RuntimeError(
                        f"Ring buffer full at order {order_id}"
                    )

                if sample_latency:
                    stage_start_ns = time.perf_counter_ns()

                order = buffer.read_order()

                if sample_latency:
                    read_times_us.append(
                        (time.perf_counter_ns() - stage_start_ns) / 1000
                    )

                if order is None:
                    raise RuntimeError(
                        f"No order read at order {order_id}"
                    )

                if sample_latency:
                    stage_start_ns = time.perf_counter_ns()

                book.add_order(*order)

                if sample_latency:
                    engine_times_us.append(
                        (time.perf_counter_ns() - stage_start_ns) / 1000
                    )
            else:
                if sample_latency:
                    stage_start_ns = time.perf_counter_ns()

                book.add_order(order_id, side, price, quantity)

                if sample_latency:
                    engine_times_us.append(
                        (time.perf_counter_ns() - stage_start_ns) / 1000
                    )

            if sample_latency:
                sampled_latencies_us.append(
                    (time.perf_counter_ns() - order_start_ns) / 1000
                )

        elapsed = time.perf_counter() - total_start

        return {
            "mode": mode,
            "orders": len(orders),
            "elapsed_seconds": elapsed,
            "throughput_ops": len(orders) / elapsed,
            "sample_count": len(sampled_latencies_us),
            "sample_interval": LATENCY_SAMPLE_INTERVAL,
            "sampled_average_latency_us": statistics.mean(
                sampled_latencies_us
            ),
            "sampled_median_latency_us": statistics.median(
                sampled_latencies_us
            ),
            "sampled_p95_latency_us": percentile(
                sampled_latencies_us, 95
            ),
            "sampled_p99_latency_us": percentile(
                sampled_latencies_us, 99
            ),
            "avg_write_us": (
                statistics.mean(write_times_us) if write_times_us else 0.0
            ),
            "avg_read_us": (
                statistics.mean(read_times_us) if read_times_us else 0.0
            ),
            "avg_engine_us": (
                statistics.mean(engine_times_us) if engine_times_us else 0.0
            ),
            "best_bid": book.get_best_bid(),
            "best_ask": book.get_best_ask(),
            "trades": len(book.get_trades()),
        }

    finally:
        if buffer is not None:
            buffer.close()


def warm_up():
    """Run a small unmeasured workload in both modes."""
    orders = generate_orders(1000, seed=12345)
    run_once("direct", orders)
    run_once("pipeline", orders)


def main():
    parser = argparse.ArgumentParser(
        description="ChronosMatch benchmark with sampled latency"
    )
    parser.add_argument("--orders", type=int, default=100000)
    parser.add_argument("--runs", type=int, default=7)
    args = parser.parse_args()

    if args.orders < 1:
        parser.error("--orders must be at least 1")

    if args.runs < 1:
        parser.error("--runs must be at least 1")

    print("ChronosMatch Benchmark V2")
    print("=" * 52)
    print(f"Orders per trial: {args.orders:,}")
    print(f"Measured trials per mode: {args.runs}")
    print(f"Latency sample interval: every {LATENCY_SAMPLE_INTERVAL} orders")
    print("Pipeline mode: single-process ring-buffer path")
    print("Warming up both modes...")

    warm_up()
    results = []

    for run_number in range(1, args.runs + 1):
        orders = generate_orders(args.orders, seed=1000 + run_number)

        modes = (
            ("direct", "pipeline")
            if run_number % 2 == 1
            else ("pipeline", "direct")
        )

        for mode in modes:
            result = run_once(mode, orders)
            result["run"] = run_number
            results.append(result)

            print(
                f"\nRun {run_number}/{args.runs} | {mode:8} | "
                f"{result['throughput_ops']:,.0f} orders/s | "
                f"elapsed {result['elapsed_seconds']:.4f} s"
            )

            print(
                f"    Sampled latency (us): "
                f"median {result['sampled_median_latency_us']:.3f} | "
                f"P95 {result['sampled_p95_latency_us']:.3f} | "
                f"P99 {result['sampled_p99_latency_us']:.3f}"
            )

            print(
                f"    Sampled engine average: "
                f"{result['avg_engine_us']:.3f} us"
            )

            if mode == "pipeline":
                print(
                    f"    Sampled buffer write: "
                    f"{result['avg_write_us']:.3f} us | "
                    f"read: {result['avg_read_us']:.3f} us"
                )

    columns = list(results[0].keys())

    with open(CSV_FILE, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        writer.writerows(results)

    print("\nSummary (median across trials)")
    print("-" * 52)

    for mode in ("direct", "pipeline"):
        mode_results = [
            result for result in results if result["mode"] == mode
        ]

        print(f"\nMode: {mode}")

        for key, label in (
            ("throughput_ops", "Throughput (orders/s)"),
            ("elapsed_seconds", "Elapsed time (s)"),
            ("sampled_median_latency_us", "Sampled median latency (us)"),
            ("sampled_p95_latency_us", "Sampled P95 latency (us)"),
            ("sampled_p99_latency_us", "Sampled P99 latency (us)"),
            ("avg_engine_us", "Sampled engine average (us)"),
        ):
            values = [result[key] for result in mode_results]
            print(f"{label}: {statistics.median(values):,.3f}")

        if mode == "pipeline":
            for key, label in (
                ("avg_write_us", "Sampled buffer write average (us)"),
                ("avg_read_us", "Sampled buffer read average (us)"),
            ):
                values = [result[key] for result in mode_results]
                print(f"{label}: {statistics.median(values):,.3f}")

    print("\nConsistency check (paired trials)")
    for run_number in range(1, args.runs + 1):
        pair = {
            result["mode"]: result
            for result in results
            if result["run"] == run_number
        }

        direct = pair["direct"]
        pipeline = pair["pipeline"]

        consistent = (
            direct["best_bid"] == pipeline["best_bid"]
            and direct["best_ask"] == pipeline["best_ask"]
            and direct["trades"] == pipeline["trades"]
        )

        print(f"Run {run_number}: {consistent}")

    print(f"\nResults saved to: {CSV_FILE}")


if __name__ == "__main__":
    main()
