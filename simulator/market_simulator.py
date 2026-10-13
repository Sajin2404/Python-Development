
import argparse
import asyncio
import random
import time

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ipc.ring_buffer import RingBuffer


async def generate_orders(buffer, total_orders=1000, batch_size=100):
    """Generate mock market orders asynchronously."""

    submitted = 0
    start_time = time.perf_counter()

    while submitted < total_orders:
        current_batch = min(batch_size, total_orders - submitted)

        for _ in range(current_batch):
            order_id = submitted + 1
            side = random.choice((1, 2))  # 1 = BUY, 2 = SELL
            price = random.randint(10000, 11000)  # Price in paise
            quantity = random.randint(1, 100)

            # Retry when the buffer is full.
            while not buffer.write_order(
                order_id, side, price, quantity
            ):
                await asyncio.sleep(0)

            submitted += 1

        # Yield control so other asynchronous tasks can run.
        await asyncio.sleep(0)

    elapsed = time.perf_counter() - start_time
    rate = submitted / elapsed if elapsed > 0 else 0

    print(f"Orders generated: {submitted}")
    print(f"Elapsed time: {elapsed:.6f} seconds")
    print(f"Generation rate: {rate:,.0f} orders/second")


async def consume_orders(buffer):
    """Consume orders while the producer is running."""

    consumed = 0

    while True:
        order = buffer.read_order()

        if order is not None:
            consumed += 1
        else:
            await asyncio.sleep(0)

        # The producer sets this attribute when finished.
        if getattr(buffer, "producer_finished", False) and order is None:
            break

    return consumed



async def run_simulation(total_orders, capacity):
    with RingBuffer(capacity=capacity) as buffer:
        buffer.producer_finished = False

        consumer_task = asyncio.create_task(consume_orders(buffer))

        # Start timing the complete producer-consumer run
        start_time = time.perf_counter()

        await generate_orders(buffer, total_orders=total_orders)
        buffer.producer_finished = True

        consumed = await consumer_task

        # Stop timing after all orders have been consumed
        elapsed = time.perf_counter() - start_time
        throughput = consumed / elapsed if elapsed > 0 else 0

        print(f"Orders consumed: {consumed}")
        print(f"End-to-end elapsed time: {elapsed:.6f} seconds")
        print(f"End-to-end throughput: {throughput:,.0f} orders/second")
        print(
            "Simulation result:",
            "PASS" if consumed == total_orders else "FAIL",
        )

def main():
    parser = argparse.ArgumentParser(
        description="ChronosMatch asynchronous market simulator"
    )
    parser.add_argument("--orders", type=int, default=1000)
    parser.add_argument("--capacity", type=int, default=1024)
    args = parser.parse_args()

    if args.orders <= 0 or args.capacity <= 0:
        parser.error("--orders and --capacity must be positive")

    asyncio.run(run_simulation(args.orders, args.capacity))


if __name__ == "__main__":
    main()