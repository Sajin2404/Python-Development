
from ipc.ring_buffer import RingBuffer
from engine.order_book import OrderBook


def main():
    # Create the shared-memory buffer and matching engine.
    with RingBuffer(capacity=16) as buffer:
        book = OrderBook(capacity=100)

        # Submit orders through the ring buffer.
        test_orders = [
            (1, 1, 10000, 5),  # BUY: 5 at 10000
            (2, 2, 9900, 3),   # SELL: 3 at 9900
            (3, 2, 10100, 4),  # SELL: 4 at 10100
        ]

        for order in test_orders:
            if not buffer.write_order(*order):
                raise RuntimeError("Ring buffer is full")

        processed = 0

        # Consume each order and send it to the Cython engine.
        while True:
            order = buffer.read_order()
            if order is None:
                break

            order_id, side, price, quantity = order
            book.add_order(order_id, side, price, quantity)
            processed += 1

        print(f"Orders processed: {processed}")
        print("Market depth:", book.get_market_depth(5))
        print("Executed trades:", book.get_trades())

        assert processed == len(test_orders)
        assert len(book.get_trades()) == 1

        print("Pipeline test: PASS")


if __name__ == "__main__":
    main()
