
import argparse
import csv
import random
import statistics
import time

from engine.order_book import OrderBook
from ipc.ring_buffer import RingBuffer


CSV_FILE = "benchmark_results.csv"


def percentile(values, percent):
    """Calculate a nearest-rank percentile."""
    if not values:
        return 0.0

    ordered = sorted(values)
    rank = max(1, (percent * len(ordered) + 99) // 100)
    return ordered[min(rank - 1, len(ordered) - 1)]


def generate_orders(count, seed):
    """Generate repeatable orders outside the timed section."""
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
    """Run one trial and return timing and market metrics."""
    book = OrderBook(capacity=len(orders) + 10)
    buffer = (
        RingBuffer(capacity=len(orders) + 10)
        if mode == "pipeline"
        else None
    )
    latencies_us = []

    try:
        # Total elapsed time includes the complete order-processing loop.
        total_start = time.perf_counter()

        for order_id, side, price, quantity in orders:
            order_start = time.perf_counter_ns()

            if buffer is not None:
                written = buffer.write_order(
                    order_id, side, price, quantity
                )
                if not written:
                    raise RuntimeError(
                        f"Ring buffer full at order {order_id}"
                    )

                order = buffer.read_order()
                if order is None:
                    raise RuntimeError(
                        f"No order read at order {order_id}"
                    )

                book.add_order(*order)
            else:
                book.add_order(order_id, side, price, quantity)

            latencies_us.append(
                (time.perf_counter_ns() - order_start) / 1000
            )

        elapsed = time.perf_counter() - total_start

        return {
            "mode": mode,
            "orders": len(latencies_us),
            "elapsed_seconds": elapsed,
            "throughput_ops": len(latencies_us) / elapsed,
            "average_latency_us": statistics.mean(latencies_us),
            "median_latency_us": statistics.median(latencies_us),
            "p95_latency_us": percentile(latencies_us, 95),
            "p99_latency_us": percentile(latencies_us, 99),
            "best_bid": book.get_best_bid(),
            "best_ask": book.get_best_ask(),
            "trades": len(book.get_trades()),
        }

    finally:
        if buffer is not None:
            buffer.close()


def warm_up():
    """Warm both modes with a small unmeasured workload."""
    warmup_orders = generate_orders(1000, seed=12345)
    run_once("direct", warmup_orders)
    run_once("pipeline", warmup_orders)


def main():
    parser = argparse.ArgumentParser(
        description="ChronosMatch repeatable benchmark"
    )
    parser.add_argument("--orders", type=int, default=10000)
    parser.add_argument("--runs", type=int, default=5)
    args = parser.parse_args()

    if args.orders < 1:
        parser.error("--orders must be at least 1")
    if args.runs < 1:
        parser.error("--runs must be at least 1")

    print("ChronosMatch Benchmark")
    print("=" * 48)
    print(f"Orders per trial: {args.orders:,}")
    print(f"Measured trials per mode: {args.runs}")
    print("Warming up both modes...")

    warm_up()
    results = []

    for run_number in range(1, args.runs + 1):
        orders = generate_orders(args.orders, seed=1000 + run_number)

        # Alternate mode order to reduce systematic ordering bias.
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
                f"Run {run_number}/{args.runs} | {mode:8} | "
                f"{result['throughput_ops']:,.0f} orders/s | "
                f"avg {result['average_latency_us']:.3f} us | "
                f"P95 {result['p95_latency_us']:.3f} us | "
                f"P99 {result['p99_latency_us']:.3f} us"
            )

    columns = [
        "run",
        "mode",
        "orders",
        "elapsed_seconds",
        "throughput_ops",
        "average_latency_us",
        "median_latency_us",
        "p95_latency_us",
        "p99_latency_us",
        "best_bid",
        "best_ask",
        "trades",
    ]

    with open(CSV_FILE, "w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=columns)
        writer.writeheader()
        writer.writerows(results)

    print("\nSummary (median across measured trials)")
    print("-" * 48)

    for mode in ("direct", "pipeline"):
        mode_results = [
            result for result in results if result["mode"] == mode
        ]

        print(f"\nMode: {mode}")
        for key, label in (
            ("throughput_ops", "Throughput (orders/s)"),
            ("average_latency_us", "Average latency (us)"),
            ("median_latency_us", "Median latency (us)"),
            ("p95_latency_us", "P95 latency (us)"),
            ("p99_latency_us", "P99 latency (us)"),
        ):
            values = [result[key] for result in mode_results]
            print(f"{label}: {statistics.median(values):,.3f}")

        # Compare each trial against the other mode using the same orders.
        paired_results = {
            result["run"]: (
                result["best_bid"],
                result["best_ask"],
                result["trades"],
            )
            for result in results
            if result["mode"] != mode
        }

        consistency = all(
            (
                result["best_bid"],
                result["best_ask"],
                result["trades"],
            )
            == paired_results[result["run"]]
            for result in mode_results
        )

        print(f"Trade/depth consistency with other mode: {consistency}")

    print(f"\nPer-trial results saved to: {CSV_FILE}")


if __name__ == "__main__":
    main()
