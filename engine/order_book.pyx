
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


cdef int64_t _match_orders_nogil(
    Order* orders,
    PriceLevel* levels,
    int* level_count,
    Trade* trade_buffer,
    int trade_capacity,
    int* trade_count,
    int side,
    int64_t incoming_order_id,
    int64_t incoming_price,
    int64_t incoming_quantity
) noexcept nogil:
    cdef int64_t remaining = incoming_quantity
    cdef int64_t fill
    cdef int resting_slot
    cdef int i

    while remaining > 0 and level_count[0] > 0:
        if side == 1 and levels[0].price > incoming_price:
            break
        if side == 2 and levels[0].price < incoming_price:
            break

        resting_slot = levels[0].head
        if resting_slot < 0:
            break

        fill = remaining
        if orders[resting_slot].remaining < fill:
            fill = orders[resting_slot].remaining

        if fill <= 0 or trade_count[0] >= trade_capacity:
            return -1

        if side == 1:
            trade_buffer[trade_count[0]].buy_order_id = incoming_order_id
            trade_buffer[trade_count[0]].sell_order_id = orders[resting_slot].order_id
        else:
            trade_buffer[trade_count[0]].buy_order_id = orders[resting_slot].order_id
            trade_buffer[trade_count[0]].sell_order_id = incoming_order_id

        trade_buffer[trade_count[0]].price = levels[0].price
        trade_buffer[trade_count[0]].quantity = fill
        trade_count[0] += 1

        remaining -= fill
        orders[resting_slot].remaining -= fill

        if orders[resting_slot].remaining == 0:
            levels[0].head = orders[resting_slot].next

            if levels[0].head == -1:
                levels[0].tail = -1

                for i in range(level_count[0] - 1):
                    levels[i] = levels[i + 1]

                level_count[0] -= 1

    return remaining


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
                         int64_t price, bint descending) noexcept nogil:
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
                            int pos) noexcept nogil:
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
        cdef int scan_level
        cdef int scan_slot
        cdef int needed_trades = 0
        cdef int64_t remaining
        cdef int64_t scan_remaining
        cdef int64_t resting_quantity
        cdef PriceLevel* opposing_levels
        cdef int* opposing_count

        if s not in (1, 2):
            raise ValueError("side must be 1 (BUY) or 2 (SELL)")
        if oid < 0 or p <= 0 or q <= 0:
            raise ValueError(
                "order_id must be non-negative; price and quantity must be positive"
            )

        if s == 1:
            opposing_levels = self.asks
            opposing_count = &self.ask_count
        else:
            opposing_levels = self.bids
            opposing_count = &self.bid_count

        # Preflight the number of trades before mutating the book.
        scan_remaining = q
        for scan_level in range(opposing_count[0]):
            if scan_remaining <= 0:
                break

            if s == 1 and opposing_levels[scan_level].price > p:
                break
            if s == 2 and opposing_levels[scan_level].price < p:
                break

            scan_slot = opposing_levels[scan_level].head
            while scan_slot != -1 and scan_remaining > 0:
                resting_quantity = self.orders[scan_slot].remaining

                if resting_quantity > 0:
                    needed_trades += 1
                    if scan_remaining <= resting_quantity:
                        scan_remaining = 0
                    else:
                        scan_remaining -= resting_quantity

                scan_slot = self.orders[scan_slot].next

        if self.trade_count + needed_trades > self.order_capacity:
            raise MemoryError("Trade buffer capacity reached")

        # Allocate before matching so capacity errors cannot occur afterward.
        slot = self._allocate_order(oid, s, p, q)

        with nogil:
            remaining = _match_orders_nogil(
                self.orders,
                opposing_levels,
                opposing_count,
                self.trade_buffer,
                self.order_capacity,
                &self.trade_count,
                s,
                oid,
                p,
                q
            )

        if remaining < 0:
            raise RuntimeError("Native matching failed")

        # Rest any unfilled quantity at the incoming order's price.
        if remaining > 0:
            if s == 1:
                level = self._find_level(
                    self.bids, self.bid_count, p, True
                )
                if level == -1:
                    level = self._insert_level(
                        self.bids, &self.bid_count, p, True
                    )
                self.orders[slot].remaining = remaining
                self._append_order(self.bids, level, slot)
            else:
                level = self._find_level(
                    self.asks, self.ask_count, p, False
                )
                if level == -1:
                    level = self._insert_level(
                        self.asks, &self.ask_count, p, False
                    )
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