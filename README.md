
# ChronosMatch

**Zero-Copy High-Frequency Trading Engine**

ChronosMatch is an educational project exploring low-latency order matching using Python, Cython, and shared memory.

## Technologies
- Python
- Cython
- mmap and struct
- asyncio
- curses
- SQLite

## Planned Features
- Zero-copy inter-process communication
- Memory-mapped ring buffer
- Price-time priority matching engine
- Market order simulator
- Real-time latency monitoring
- Trade execution ledger

## Development Roadmap
- Week 1: Ring buffer and market simulator
- Week 2: Cython matching engine and terminal dashboard
- Week 3: Latency measurement and optimization
- Week 4: Trade persistence and final testing

## Advanced Performance Benchmarking

ChronosMatch includes an enhanced benchmarking system to compare the performance of the Cython matching engine in two execution modes:

- **Direct Engine:** Orders are submitted directly to the Cython order book.
- **Ring Buffer Pipeline:** Orders pass through the memory-mapped ring buffer before reaching the matching engine.

The benchmark includes warm-up runs, repeated trials, deterministic order generation, and consistency checks to make performance comparisons more reliable.

### Running the Benchmark

Run the benchmark with the default settings:

```powershell
python benchmark.py
```

Specify the number of orders and measured trials:

```powershell
python benchmark.py --orders 10000 --runs 3
```

### Performance Metrics

The benchmark measures:

- **Throughput:** Orders processed per second.
- **Average latency:** Average end-to-end processing time per order.
- **Median latency:** Median per-order processing time.
- **P95 latency:** 95th-percentile per-order latency.
- **P99 latency:** 99th-percentile per-order latency.
- **Buffer write latency:** Time spent writing an order to the ring buffer.
- **Buffer read latency:** Time spent reading an order from the ring buffer.
- **Engine latency:** Time spent processing an order in the matching engine.

Results from individual trials are saved to `benchmark_results.csv`.

### Sample Benchmark Results

The following results were recorded locally with 10,000 orders per trial and three measured trials per mode.

| Metric | Direct Engine | Ring Buffer Pipeline |
|---|---:|---:|
| Median throughput across trials | 841,156 orders/s | 209,951 orders/s |
| Median of trial average latency | 0.896 µs | 4.376 µs |
| Median engine-stage latency | 0.507 µs | 0.828 µs |

These results show that the direct engine achieved higher throughput in this test. The ring-buffer pipeline adds write and read operations, increasing end-to-end processing time.

*Note: These are preliminary measurements from a local development environment. Results vary with hardware, workload, operating-system scheduling, and measurement overhead. They are not production HFT performance guarantees.*

### Benchmark Consistency Validation

After each paired trial, the benchmark compares the following results between execution modes:

- Best bid price.
- Best ask price.
- Number of executed trades.

All three paired trials in the recorded benchmark returned successful consistency checks. This provides evidence that both modes produced matching final values for these checks under the tested workload; it does not prove complete behavioral equivalence for every possible order sequence.

## Testing and Validation

Run the full unit-test suite:

```powershell
python -m unittest discover -s tests -v
```

Run the pipeline integration test:

```powershell
python pipeline_test.py
```

These checks cover the implemented ring buffer, Cython order book, and integrated order-processing pipeline.

## Current Implementation Notes

- The matching engine is implemented in Cython and compiled as a Python extension.
- The ring buffer uses memory-mapped storage for order records.
- The dashboard supports direct-engine and ring-buffer-pipeline execution modes.
- The current pipeline operates within a single process. Cross-process synchronization and a fully lock-free IPC implementation are not yet established.
- Benchmark timings are intended for development and comparative analysis, not as guarantees of exchange-grade latency or reliability.

## Future Improvements

- Implement and validate synchronized cross-process communication.
- Optimize order matching and reduce latency-measurement overhead.
- Expand stress, concurrency, and failure-recovery tests.
- Benchmark larger workloads and longer test durations.
- Add historical benchmark comparisons and performance visualizations.

## Project Status
Current Stage: Working Prototype — Performance Benchmarking and Optimization

## Disclaimer
For educational and benchmarking purposes only. Not connected to a live financial exchange.
