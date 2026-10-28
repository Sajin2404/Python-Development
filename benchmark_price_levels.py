import statistics
import time

from engine.order_book import OrderBook

ORDERS = 20_000
TRIALS = 5
WARMUPS = 2


def run_matching_workload():
    """Measure repeated matching at a single price."""
    book = OrderBook(capacity=ORDERS * 2)

    for i in range(ORDERS):
        book.add_order(2 * i, 1, 10_000, 1)
        book.add_order(2 * i + 1, 2, 10_000, 1)

    assert len(book.get_trades()) == ORDERS


def run_non_crossing_workload():
    """Measure adding orders that do not cross."""
    book = OrderBook(capacity=ORDERS)

    for i in range(ORDERS):
        book.add_order(i, 1, 30_000 - i, 1)

    assert book.get_best_bid() == 30_000


def run_many_price_levels_workload():
    """Measure insertion of distinct bid price levels."""
    level_count = 2_000
    book = OrderBook(capacity=level_count)

    # Ascending prices force new best bids to be inserted at the front.
    for i in range(level_count):
        book.add_order(i, 1, 10_000 + i, 1)

    assert book.get_best_bid() == 11_999

def benchmark(name, workload):
    for _ in range(WARMUPS):
        workload()

    measurements = []

    for trial in range(1, TRIALS + 1):
        start = time.perf_counter()

        workload()

        elapsed = time.perf_counter() - start
        throughput = ORDERS / elapsed

        measurements.append(elapsed)

        print(
            f"{name} | Trial {trial}: "
            f"{elapsed:.4f} s | "
            f"{throughput:,.0f} orders/s"
        )

    median_elapsed = statistics.median(measurements)
    median_throughput = ORDERS / median_elapsed

    print(
        f"{name} | Median: "
        f"{median_elapsed:.4f} s | "
        f"{median_throughput:,.0f} orders/s"
    )
    print()


if __name__ == "__main__":
    print("ChronosMatch Price-Level Benchmark")
    print(f"Orders per workload: {ORDERS:,}")
    print(f"Warm-up runs: {WARMUPS}")
    print(f"Measured trials: {TRIALS}")
    print()

    benchmark("Matching", run_matching_workload)
    benchmark("Non-crossing", run_non_crossing_workload)
    benchmark("Many price levels", run_many_price_levels_workload)