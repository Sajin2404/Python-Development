
# cython: language_level=3, boundscheck=False, wraparound=False

from libc.stdint cimport int64_t
from libc.stdlib cimport malloc, free

cdef struct Trade:
    int64_t resting_order_id
    int64_t fill_quantity


cdef int64_t match_orders(
    int64_t incoming_quantity,
    int64_t* resting_ids,
    int64_t* resting_quantities,
    int resting_count,
    Trade* trades,
    int trade_capacity,
    int* trade_count
) noexcept nogil:
    cdef int i
    cdef int64_t remaining = incoming_quantity
    cdef int64_t fill

    trade_count[0] = 0

    for i in range(resting_count):
        if remaining <= 0:
            break

        if resting_quantities[i] <= 0:
            continue

        if remaining < resting_quantities[i]:
            fill = remaining
        else:
            fill = resting_quantities[i]

        if trade_count[0] >= trade_capacity:
            return -1

        trades[trade_count[0]].resting_order_id = resting_ids[i]
        trades[trade_count[0]].fill_quantity = fill
        trade_count[0] += 1

        remaining -= fill
        resting_quantities[i] -= fill

    return remaining
def run_matching(
    incoming_quantity,
    resting_ids,
    resting_quantities,
    trade_capacity
):
    cdef int64_t incoming = incoming_quantity
    cdef int count = len(resting_ids)
    cdef int capacity = trade_capacity
    cdef int trade_count = 0
    cdef int64_t remaining
    cdef int i

    cdef int64_t* ids = NULL
    cdef int64_t* quantities = NULL
    cdef Trade* trades = NULL

    if incoming <= 0:
        raise ValueError("Incoming quantity must be positive")
    if len(resting_quantities) != count:
        raise ValueError("IDs and quantities must have equal lengths")
    if capacity < 0:
        raise ValueError("Trade capacity cannot be negative")
    if capacity < count:
        raise ValueError("Trade capacity must be at least the resting order count")

    if count > 0:
        ids = <int64_t*>malloc(count * sizeof(int64_t))
        quantities = <int64_t*>malloc(count * sizeof(int64_t))

    if capacity > 0:
        trades = <Trade*>malloc(capacity * sizeof(Trade))

    if ((count > 0 and (ids == NULL or quantities == NULL))
            or (capacity > 0 and trades == NULL)):
        if ids != NULL:
            free(ids)
        if quantities != NULL:
            free(quantities)
        if trades != NULL:
            free(trades)
        raise MemoryError("Could not allocate matching buffers")

    try:
        for i in range(count):
            ids[i] = resting_ids[i]
            quantities[i] = resting_quantities[i]
            if quantities[i] < 0:
                raise ValueError("Resting quantities cannot be negative")

        with nogil:
            remaining = match_orders(
                incoming, ids, quantities, count,
                trades, capacity, &trade_count
            )

        if remaining == -1:
            raise RuntimeError("Trade buffer capacity exceeded")

        result = {
            "remaining": remaining,
            "trades": [
                {
                    "resting_order_id": trades[i].resting_order_id,
                    "quantity": trades[i].fill_quantity,
                }
                for i in range(trade_count)
            ],
            "resting_quantities": [quantities[i] for i in range(count)],
        }
        return result
    finally:
        if ids != NULL:
            free(ids)
        if quantities != NULL:
            free(quantities)
        if trades != NULL:
            free(trades)
