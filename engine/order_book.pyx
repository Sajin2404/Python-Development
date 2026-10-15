
# cython: language_level=3, boundscheck=False, wraparound=False, initializedcheck=False

from libc.stdint cimport int64_t, uint64_t
from libc.stdlib cimport malloc, free
from libc.limits cimport INT_MAX


cdef struct Order:
    int64_t order_id
    int64_t price
    int64_t quantity
    int64_t remaining
    int side
    int next


cdef struct PriceLevel:
    int64_t price
    int head
    int tail


cdef struct Trade:
    int64_t buy_order_id
    int64_t sell_order_id
    int64_t price
    int64_t quantity

    
cdef class OrderBook:
    cdef Order* orders
    cdef PriceLevel* bids
    cdef PriceLevel* asks
    cdef Trade* trade_buffer
    cdef int order_capacity
    cdef int bid_count
    cdef int ask_count
    cdef int next_order_slot
    cdef int trade_count

    def __cinit__(self, int capacity=1000000):
        if capacity <= 0:
            raise ValueError("capacity must be positive")

        
        self.order_capacity = capacity
        self.bid_count = 0
        self.ask_count = 0
        self.next_order_slot = 0
        self.trade_count = 0
        self.trade_buffer = NULL

        self.orders = <Order*>malloc(capacity * sizeof(Order))
        self.bids = <PriceLevel*>malloc(capacity * sizeof(PriceLevel))
        self.asks = <PriceLevel*>malloc(capacity * sizeof(PriceLevel))
        self.trade_buffer = <Trade*>malloc(capacity * sizeof(Trade))

        if (
             self.orders == NULL
             or self.bids == NULL
             or self.asks == NULL
             or self.trade_buffer == NULL
           ):
            if self.orders != NULL:
                free(self.orders)
                self.orders = NULL
            if self.bids != NULL:
                free(self.bids)
                self.bids = NULL
            if self.asks != NULL:
                free(self.asks)
                self.asks = NULL    
            if self.trade_buffer != NULL:
                free(self.trade_buffer)
                self.trade_buffer = NULL
            raise MemoryError("Could not allocate order book")    

    def __dealloc__(self):
        if self.orders != NULL:
            free(self.orders)
        if self.bids != NULL:
            free(self.bids)
        if self.asks != NULL:
            free(self.asks)
        if self.trade_buffer != NULL:
            free(self.trade_buffer)

    cdef int _find_level(self, PriceLevel* levels, int count,
                         int64_t price, bint descending) noexcept:
        cdef int i
        for i in range(count):
            if levels[i].price == price:
                return i
            if descending and levels[i].price < price:
                break
            if not descending and levels[i].price > price:
                break
        return -1

    cdef int _insert_level(self, PriceLevel* levels, int* count,
                           int64_t price, bint descending) except -1:
        cdef int pos = 0
        cdef int i

        if count[0] >= self.order_capacity:
            raise MemoryError("Price level capacity reached")

        while pos < count[0]:
            if descending and levels[pos].price < price:
                break
            if not descending and levels[pos].price > price:
                break
            pos += 1

        for i in range(count[0], pos, -1):
            levels[i] = levels[i - 1]

        levels[pos].price = price
        levels[pos].head = -1
        levels[pos].tail = -1
        count[0] += 1
        return pos

    cdef void _remove_level(self, PriceLevel* levels, int* count,
                            int pos) noexcept:
        cdef int i
        for i in range(pos, count[0] - 1):
            levels[i] = levels[i + 1]
        count[0] -= 1

    cdef int _allocate_order(self, int64_t order_id, int side,
                             int64_t price, int64_t quantity) except -1:
        cdef int slot
        if self.next_order_slot >= self.order_capacity:
            raise MemoryError(
                "Order capacity reached; create a new book or increase capacity"
            )
        slot = self.next_order_slot
        self.next_order_slot += 1

        self.orders[slot].order_id = order_id
        self.orders[slot].side = side
        self.orders[slot].price = price
        self.orders[slot].quantity = quantity
        self.orders[slot].remaining = quantity
        self.orders[slot].next = -1
        return slot

    cdef void _append_order(self, PriceLevel* levels, int level,
                            int slot) noexcept:
        if levels[level].tail == -1:
            levels[level].head = slot
            levels[level].tail = slot
        else:
            self.orders[levels[level].tail].next = slot
            levels[level].tail = slot

    def add_order(self, order_id, side, price, quantity):
        cdef int64_t oid = order_id
        cdef int64_t p = price
        cdef int64_t q = quantity
        cdef int s = side
        cdef int slot
        cdef int level
        cdef int resting_slot
        cdef int64_t fill
        cdef int64_t remaining = q

        if s not in (1, 2):
            raise ValueError("side must be 1 (BUY) or 2 (SELL)")
        if oid < 0 or p <= 0 or q <= 0:
            raise ValueError("order_id must be non-negative; price and quantity must be positive")

        slot = self._allocate_order(oid, s, p, q)

        if s == 1:
            while remaining > 0 and self.ask_count > 0:
                if self.asks[0].price > p:
                    break
                level = 0
                resting_slot = self.asks[level].head
                fill = remaining
                if self.orders[resting_slot].remaining < fill:
                    fill = self.orders[resting_slot].remaining

                if self.trade_count >= self.order_capacity:
                    raise MemoryError("Trade buffer capacity reached")

                self.trade_buffer[self.trade_count].buy_order_id = oid
                self.trade_buffer[self.trade_count].sell_order_id = self.orders[resting_slot].order_id
                self.trade_buffer[self.trade_count].price = self.asks[level].price
                self.trade_buffer[self.trade_count].quantity = fill
                self.trade_count += 1

                remaining -= fill
                self.orders[resting_slot].remaining -= fill

                if self.orders[resting_slot].remaining == 0:
                    self.asks[level].head = self.orders[resting_slot].next
                    if self.asks[level].head == -1:
                        self.asks[level].tail = -1
                        self._remove_level(self.asks, &self.ask_count, level)

            if remaining > 0:
                level = self._find_level(self.bids, self.bid_count, p, True)
                if level == -1:
                    level = self._insert_level(self.bids, &self.bid_count, p, True)
                self.orders[slot].remaining = remaining
                self._append_order(self.bids, level, slot)

        else:
            while remaining > 0 and self.bid_count > 0:
                if self.bids[0].price < p:
                    break
                level = 0
                resting_slot = self.bids[level].head
                fill = remaining
                if self.orders[resting_slot].remaining < fill:
                    fill = self.orders[resting_slot].remaining

                if self.trade_count >= self.order_capacity:
                    raise MemoryError("Trade buffer capacity reached")

                self.trade_buffer[self.trade_count].buy_order_id = self.orders[resting_slot].order_id
                self.trade_buffer[self.trade_count].sell_order_id = oid
                self.trade_buffer[self.trade_count].price = self.bids[level].price
                self.trade_buffer[self.trade_count].quantity = fill
                self.trade_count += 1

                remaining -= fill
                self.orders[resting_slot].remaining -= fill

                if self.orders[resting_slot].remaining == 0:
                    self.bids[level].head = self.orders[resting_slot].next
                    if self.bids[level].head == -1:
                        self.bids[level].tail = -1
                        self._remove_level(self.bids, &self.bid_count, level)

            if remaining > 0:
                level = self._find_level(self.asks, self.ask_count, p, False)
                if level == -1:
                    level = self._insert_level(self.asks, &self.ask_count, p, False)
                self.orders[slot].remaining = remaining
                self._append_order(self.asks, level, slot)

        return remaining

    def get_best_bid(self):
        if self.bid_count == 0:
            return None
        return self.bids[0].price

    def get_best_ask(self):
        if self.ask_count == 0:
            return None
        return self.asks[0].price

    def get_trades(self):
        cdef int i
        cdef list trades = []

        for i in range(self.trade_count):
            trades.append({
                "buy_order_id": self.trade_buffer[i].buy_order_id,
                "sell_order_id": self.trade_buffer[i].sell_order_id,
                "price": self.trade_buffer[i].price,
                "quantity": self.trade_buffer[i].quantity,
            })

        return trades