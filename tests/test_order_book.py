
import unittest

from engine.order_book import OrderBook


class TestOrderBook(unittest.TestCase):
    def test_buy_and_sell_match(self):
        book = OrderBook()

        book.add_order(1, 1, 10000, 10)  # Buy 10 at 100.00
        book.add_order(2, 2, 10000, 10)  # Sell 10 at 100.00

        trades = book.get_trades()

        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0]["buy_order_id"], 1)
        self.assertEqual(trades[0]["sell_order_id"], 2)
        self.assertEqual(trades[0]["price"], 10000)
        self.assertEqual(trades[0]["quantity"], 10)

    def test_partial_fill(self):
        book = OrderBook()

        book.add_order(1, 1, 10000, 10)
        remaining = book.add_order(2, 2, 10000, 4)

        self.assertEqual(remaining, 0)
        self.assertEqual(book.get_trades()[0]["quantity"], 4)
        self.assertEqual(book.get_best_bid(), 10000)

    def test_price_priority(self):
        book = OrderBook()

        book.add_order(1, 1, 10000, 5)
        book.add_order(2, 1, 10100, 5)
        book.add_order(3, 2, 10000, 5)

        trades = book.get_trades()

        self.assertEqual(trades[0]["buy_order_id"], 2)
        self.assertEqual(trades[0]["price"], 10100)

    def test_fifo_at_same_price(self):
        book = OrderBook()

        book.add_order(1, 1, 10000, 5)
        book.add_order(2, 1, 10000, 5)
        book.add_order(3, 2, 10000, 7)

        trades = book.get_trades()

        self.assertEqual(trades[0]["buy_order_id"], 1)
        self.assertEqual(trades[0]["quantity"], 5)
        self.assertEqual(trades[1]["buy_order_id"], 2)
        self.assertEqual(trades[1]["quantity"], 2)


if __name__ == "__main__":
    unittest.main()
