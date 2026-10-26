import time
from engine.order_book import OrderBook


def test_exact_match():
    book = OrderBook()

    book.add_order(1, 1, 10000, 10)
    book.add_order(2, 2, 10000, 10)

    trades = book.get_trades()

    assert len(trades) == 1
    assert trades[0] == {
        "buy_order_id": 1,
        "sell_order_id": 2,
        "price": 10000,
        "quantity": 10,
    }

    assert book.get_best_bid() is None
    assert book.get_best_ask() is None

    print("PASS: Exact-price matching")


def test_no_match_when_prices_do_not_cross():
    book = OrderBook()

    book.add_order(1, 1, 9900, 10)
    book.add_order(2, 2, 10000, 10)

    assert len(book.get_trades()) == 0
    assert book.get_best_bid() == 9900
    assert book.get_best_ask() == 10000

    print("PASS: Non-crossing orders do not match")


def test_partial_fill():
    book = OrderBook()

    book.add_order(1, 1, 10000, 10)
    remaining = book.add_order(2, 2, 10000, 4)

    trades = book.get_trades()

    assert remaining == 0
    assert len(trades) == 1
    assert trades[0]["quantity"] == 4
    assert book.get_best_bid() == 10000

    print("PASS: Partial fill")


def test_large_matching_workload():
    pair_count = 10000
    book = OrderBook(capacity=pair_count * 2)

    start = time.perf_counter_ns()

    for i in range(1, pair_count + 1):
        buy_id = 2 * i
        sell_id = buy_id + 1

        book.add_order(buy_id, 1, 10000, 1)
        book.add_order(sell_id, 2, 10000, 1)

    elapsed_ns = time.perf_counter_ns() - start
    trades = book.get_trades()

    assert len(trades) == pair_count
    assert all(trade["quantity"] == 1 for trade in trades)

    print(f"PASS: {pair_count:,} matching pairs")
    print(f"Trades recorded: {len(trades):,}")
    print(f"Total elapsed time: {elapsed_ns / 1_000_000:.3f} ms")
    print(f"Average time per pair: {elapsed_ns / pair_count:.1f} ns")


if __name__ == "__main__":
    test_exact_match()
    test_no_match_when_prices_do_not_cross()
    test_partial_fill()
    test_large_matching_workload()

    print("\nENGINE VERIFICATION: ALL TESTS PASSED")
