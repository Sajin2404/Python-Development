
import argparse
import asyncio
import random
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ipc.ring_buffer import RingBuffer
from engine.order_book import OrderBook


async def generate_orders(buffer, total_orders=1000, batch_size=100):
    """Generate mock orders and publish them to the ring buffer."""
    submitted = 0
    start_time = time.perf_counter()

    while submitted < total_orders:
        current_batch = min(batch_size, total_orders - submitted)

        for _ in range(current_batch):
            order_id = submitted + 1
            side = random.choice((1, 2))
            price = random.randint(10000, 11000)
            quantity = random.randint(1, 100)

            # Wait until there is space in the buffer.
            while not buffer.write_order(
                order_id, side, price, quantity
            ):
                await asyncio.sleep(0)

            submitted += 1

        await asyncio.sleep(0)

    elapsed = time.perf_counter() - start_time
    rate = submitted / elapsed if elapsed > 0 else 0

    print(f"Orders generated: {submitted}")
    print(f"Generation time: {elapsed:.6f} seconds")
    print(f"Generation rate: {rate:,.0f} orders/second")


async def consume_orders(buffer, book):
    """Read orders from the ring buffer and process them in Cython."""
    consumed = 0

    while True:
        order = buffer.read_order()

        if order is not None:
            order_id, side, price, quantity = order
            book.add_order(order_id, side, price, quantity)
            consumed += 1
        else:
            if getattr(buffer, "producer_finished", False):
                break
            await asyncio.sleep(0)

    return consumed


async def run_simulation(total_orders, capacity):
    with RingBuffer(capacity=capacity) as buffer:
        book = OrderBook(capacity=max(total_orders, 1))
        buffer.producer_finished = False

        consumer_task = asyncio.create_task(
            consume_orders(buffer, book)
        )

        start_time = time.perf_counter()

        await generate_orders(
            buffer,
            total_orders=total_orders,
        )
        buffer.producer_finished = True

        consumed = await consumer_task

        elapsed = time.perf_counter() - start_time
        throughput = consumed / elapsed if elapsed > 0 else 0
        trades = book.get_trades()
        depth = book.get_market_depth(5)

        print(f"\nOrders processed by engine: {consumed}")
        print(f"Executed trades: {len(trades)}")
        print(f"End-to-end elapsed time: {elapsed:.6f} seconds")
        print(f"End-to-end throughput: {throughput:,.0f} orders/second")
        print("Final market depth:", depth)
        print(
            "Simulation result:",
            "PASS" if consumed == total_orders else "FAIL",
        )

        if consumed != total_orders:
            raise RuntimeError("Not all generated orders were processed")


def main():
    parser = argparse.ArgumentParser(
        description="ChronosMatch ring-buffer-to-Cython simulator"
    )
    parser.add_argument("--orders", type=int, default=1000)
    parser.add_argument("--capacity", type=int, default=1024)
    args = parser.parse_args()

    if args.orders <= 0 or args.capacity <= 0:
        parser.error("--orders and --capacity must be positive")

    asyncio.run(run_simulation(args.orders, args.capacity))


if __name__ == "__main__":
    main()
