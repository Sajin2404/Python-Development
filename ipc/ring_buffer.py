import mmap
import os
import struct
import tempfile


# Order record format:
# Q = unsigned 64-bit order ID
# B = unsigned 8-bit side (1 = BUY, 2 = SELL)
# Q = unsigned 64-bit price in paise
# I = unsigned 32-bit quantity
ORDER_FORMAT = "<QBQI"
ORDER_SIZE = struct.calcsize(ORDER_FORMAT)


class RingBuffer:
    """Fixed-capacity memory-mapped FIFO ring buffer."""

    def __init__(self, capacity=1024):
        if capacity <= 0:
            raise ValueError("Capacity must be positive")

        self.capacity = capacity
        self.read_index = 0
        self.write_index = 0
        self.count = 0

        self._temp = tempfile.NamedTemporaryFile(delete=False)
        self.filename = self._temp.name
        self._temp.close()

        self.file = open(self.filename, "r+b")
        self.file.truncate(capacity * ORDER_SIZE)

        self.memory = mmap.mmap(
            self.file.fileno(),
            capacity * ORDER_SIZE,
            access=mmap.ACCESS_WRITE,
        )

    def write_order(self, order_id, side, price, quantity):
        if side not in (1, 2):
            raise ValueError("Side must be 1 (BUY) or 2 (SELL)")

        if self.count >= self.capacity:
            return False

        packed = struct.pack(
            ORDER_FORMAT, order_id, side, price, quantity
        )

        offset = self.write_index * ORDER_SIZE
        self.memory[offset:offset + ORDER_SIZE] = packed

        self.write_index = (self.write_index + 1) % self.capacity
        self.count += 1
        return True

    def read_order(self):
        if self.count == 0:
            return None

        offset = self.read_index * ORDER_SIZE
        packed = self.memory[offset:offset + ORDER_SIZE]
        order = struct.unpack(ORDER_FORMAT, packed)

        self.read_index = (self.read_index + 1) % self.capacity
        self.count -= 1
        return order

    def close(self):
        self.memory.close()
        self.file.close()
        try:
            os.unlink(self.filename)
        except FileNotFoundError:
            pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()


if __name__ == "__main__":
    with RingBuffer(capacity=4) as buffer:
        buffer.write_order(1001, 1, 12550, 10)
        buffer.write_order(1002, 2, 12500, 5)

        print("First order:", buffer.read_order())
        print("Second order:", buffer.read_order())
        print("Empty buffer:", buffer.read_order())
