
import unittest

from engine.matching_core import run_matching


class TestMatchingCore(unittest.TestCase):

    def test_full_and_partial_fills(self):
        result = run_matching(10, [101, 102], [6, 8], 2)

        self.assertEqual(result["remaining"], 0)
        self.assertEqual(
            result["trades"],
            [
                {"resting_order_id": 101, "quantity": 6},
                {"resting_order_id": 102, "quantity": 4},
            ],
        )
        self.assertEqual(result["resting_quantities"], [0, 4])

    def test_single_order_partial_fill(self):
        result = run_matching(4, [201, 202], [7, 5], 2)

        self.assertEqual(result["remaining"], 0)
        self.assertEqual(
            result["trades"],
            [{"resting_order_id": 201, "quantity": 4}],
        )
        self.assertEqual(result["resting_quantities"], [3, 5])

    def test_invalid_quantity(self):
        with self.assertRaises(ValueError):
            run_matching(0, [101], [5], 1)


if __name__ == "__main__":
    unittest.main()
