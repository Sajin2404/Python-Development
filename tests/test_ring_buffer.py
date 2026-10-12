
import unittest
from ipc.ring_buffer import RingBuffer


class TestRingBuffer(unittest.TestCase):

    def test_write_and_read_order(self):
        with RingBuffer(capacity=4) as buffer:
            self.assertTrue(buffer.write_order(1001, 1, 12550, 10))
            self.assertEqual(
                buffer.read_order(),
                (1001, 1, 12550, 10),
            )

    def test_empty_buffer(self):
        with RingBuffer(capacity=4) as buffer:
            self.assertIsNone(buffer.read_order())

    def test_full_buffer(self):
        with RingBuffer(capacity=2) as buffer:
            self.assertTrue(buffer.write_order(1, 1, 10000, 5))
            self.assertTrue(buffer.write_order(2, 2, 10100, 3))

            # A full buffer must reject another order.
            self.assertFalse(buffer.write_order(3, 1, 9900, 2))

    def test_fifo_order(self):
        with RingBuffer(capacity=4) as buffer:
            buffer.write_order(1, 1, 10000, 1)
            buffer.write_order(2, 2, 10100, 2)

            self.assertEqual(
                buffer.read_order(), (1, 1, 10000, 1)
            )
            self.assertEqual(
                buffer.read_order(), (2, 2, 10100, 2)
            )

    def test_wraparound(self):
        with RingBuffer(capacity=2) as buffer:
            buffer.write_order(1, 1, 10000, 1)
            buffer.write_order(2, 2, 10100, 1)

            buffer.read_order()
            buffer.write_order(3, 1, 9900, 1)

            self.assertEqual(
                buffer.read_order(), (2, 2, 10100, 1)
            )
            self.assertEqual(
                buffer.read_order(), (3, 1, 9900, 1)
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
