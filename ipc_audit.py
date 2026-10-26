import argparse
import mmap
import os
import struct
import tempfile
import time
import multiprocessing as mp

# Binary record:
# Q = order ID (uint64)
# B = side (uint8)
# Q = price (uint64)
# I = quantity (uint32)
ORDER_FORMAT = "<QBQI"
ORDER_SIZE = struct.calcsize(ORDER_FORMAT)

HEADER_FORMAT = "<QQQ"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)

READ_INDEX_OFFSET = 0
WRITE_INDEX_OFFSET = 8
TOTAL_ORDERS_OFFSET = 16


def producer(filename, capacity, total_orders, ready, done):
    """Write binary orders into a shared memory-mapped ring buffer."""
    record_area_size = capacity * ORDER_SIZE

    with open(filename, "r+b") as file:
        with mmap.mmap(file.fileno(), 0, access=mmap.ACCESS_WRITE) as memory:
            ready.wait()

            for order_id in range(1, total_orders + 1):
                # Wait if the ring buffer is full.
                while True:
                    read_index = struct.unpack_from(
                        "<Q", memory, READ_INDEX_OFFSET
                    )[0]
                    write_index = struct.unpack_from(
                        "<Q", memory, WRITE_INDEX_OFFSET
                    )[0]

                    if write_index - read_index < capacity:
                        break

                    time.sleep(0)

                slot = write_index % capacity
                offset = HEADER_SIZE + slot * ORDER_SIZE

                side = 1 if order_id % 2 else 2
                price = 10000 + order_id % 1000
                quantity = 1 + order_id % 100

                struct.pack_into(
                    ORDER_FORMAT,
                    memory,
                    offset,
                    order_id,
                    side,
                    price,
                    quantity,
                )

                # Publish the record only after writing its data.
                struct.pack_into(
                    "<Q",
                    memory,
                    WRITE_INDEX_OFFSET,
                    write_index + 1,
                )

            struct.pack_into(
                "<Q",
                memory,
                TOTAL_ORDERS_OFFSET,
                total_orders,
            )

            done.set()


def consumer(filename, capacity, total_orders, ready, done, result_queue):
    """Read and validate orders from the shared memory-mapped buffer."""
    received = 0
    checksum = 0
    errors = 0
    expected_id = 1

    with open(filename, "r+b") as file:
        with mmap.mmap(file.fileno(), 0, access=mmap.ACCESS_WRITE) as memory:
            ready.wait()

            while received < total_orders:
                read_index = struct.unpack_from(
                    "<Q", memory, READ_INDEX_OFFSET
                )[0]
                write_index = struct.unpack_from(
                    "<Q", memory, WRITE_INDEX_OFFSET
                )[0]

                if read_index >= write_index:
                    if done.is_set():
                        break
                    time.sleep(0)
                    continue

                slot = read_index % capacity
                offset = HEADER_SIZE + slot * ORDER_SIZE

                order_id, side, price, quantity = struct.unpack_from(
                    ORDER_FORMAT, memory, offset
                )

                if order_id != expected_id:
                    errors += 1

                if side not in (1, 2):
                    errors += 1

                if price != 10000 + order_id % 1000:
                    errors += 1

                if quantity != 1 + order_id % 100:
                    errors += 1

                checksum += order_id
                expected_id += 1
                received += 1

                # Release the consumed slot.
                struct.pack_into(
                    "<Q",
                    memory,
                    READ_INDEX_OFFSET,
                    read_index + 1,
                )

    result_queue.put((received, checksum, errors))


def run_audit(total_orders, capacity):
    if total_orders <= 0:
        raise ValueError("total_orders must be positive")

    if capacity <= 0:
        raise ValueError("capacity must be positive")

    file_size = HEADER_SIZE + capacity * ORDER_SIZE
    expected_checksum = total_orders * (total_orders + 1) // 2

    with tempfile.NamedTemporaryFile(delete=False) as file:
        filename = file.name
        file.truncate(file_size)

    # Initialize shared indices.
    with open(filename, "r+b") as file:
        with mmap.mmap(file.fileno(), 0, access=mmap.ACCESS_WRITE) as memory:
            struct.pack_into("<Q", memory, READ_INDEX_OFFSET, 0)
            struct.pack_into("<Q", memory, WRITE_INDEX_OFFSET, 0)
            struct.pack_into("<Q", memory, TOTAL_ORDERS_OFFSET, 0)

    context = mp.get_context("spawn")
    ready = context.Event()
    done = context.Event()
    result_queue = context.Queue()

    writer = context.Process(
        target=producer,
        args=(filename, capacity, total_orders, ready, done),
    )

    reader = context.Process(
        target=consumer,
        args=(
            filename,
            capacity,
            total_orders,
            ready,
            done,
            result_queue,
        ),
    )

    try:
        writer.start()
        reader.start()

        start = time.perf_counter()
        ready.set()

        writer.join()
        reader.join()
        elapsed = time.perf_counter() - start

        if writer.exitcode != 0 or reader.exitcode != 0:
            raise RuntimeError(
                f"Process failure: producer={writer.exitcode}, "
                f"consumer={reader.exitcode}"
            )

        received, checksum, errors = result_queue.get(timeout=5)

        throughput = received / elapsed if elapsed else 0

        print("\nChronosMatch IPC Audit")
        print("=" * 40)
        print(f"Producer PID: {writer.pid}")
        print(f"Consumer PID: {reader.pid}")
        print(f"Orders requested: {total_orders:,}")
        print(f"Orders received: {received:,}")
        print(f"Elapsed time: {elapsed:.3f} seconds")
        print(f"Throughput: {throughput:,.0f} orders/second")
        print(f"Checksum valid: {checksum == expected_checksum}")
        print(f"Validation errors: {errors}")

        passed = (
            received == total_orders
            and checksum == expected_checksum
            and errors == 0
        )

        print(f"IPC Audit: {'PASS' if passed else 'FAIL'}")

    finally:
        for process in (writer, reader):
            if process.is_alive():
                process.terminate()
                process.join()

        result_queue.close()

        try:
            os.unlink(filename)
        except FileNotFoundError:
            pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="ChronosMatch cross-process IPC audit"
    )
    parser.add_argument("--orders", type=int, default=1_000_000)
    parser.add_argument("--capacity", type=int, default=4096)
    args = parser.parse_args()

    run_audit(args.orders, args.capacity)