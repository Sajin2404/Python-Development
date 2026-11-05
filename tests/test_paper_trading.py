import unittest
from paper_trading import PaperTradingEngine

class TestPaperTradingEngine(unittest.TestCase):
    def setUp(self):
        self.engine = PaperTradingEngine(starting_cash=10000)

    def test_buy_matches_synthetic_ask_and_updates_position(self):
        order = self.engine.place_limit_order("RELIANCE", "BUY", 1, 150, 149)
        self.assertEqual(order["status"], "FILLED")
        self.assertEqual(order["filled_quantity"], 1)
        self.assertEqual(len(self.engine.trades()), 1)
        portfolio = self.engine.portfolio({"RELIANCE": 149})
        self.assertEqual(portfolio["positions"][0]["quantity"], 1)

    def test_open_sell_can_be_cancelled_and_shares_released(self):
        self.engine.place_limit_order("RELIANCE", "BUY", 1, 150, 149)
        sell = self.engine.place_limit_order("RELIANCE", "SELL", 1, 160, 149)
        self.assertEqual(sell["status"], "OPEN")
        self.assertTrue(self.engine.cancel_order(sell["order_id"]))
        self.assertEqual(self.engine.orders()[0]["status"], "CANCELLED")
        # The share is available again after cancellation.
        second = self.engine.place_limit_order("RELIANCE", "SELL", 1, 160, 149)
        self.assertEqual(second["status"], "OPEN")

    def test_buy_reservation_is_released_on_cancel(self):
        buy = self.engine.place_limit_order("RELIANCE", "BUY", 1, 100, 200)
        self.assertEqual(buy["status"], "OPEN")
        before = self.engine.cash
        self.assertTrue(self.engine.cancel_order(buy["order_id"]))
        self.assertGreater(self.engine.cash, before)

if __name__ == "__main__":
    unittest.main()
