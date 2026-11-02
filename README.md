# optipy

Measure the **speed and memory** of Python code, then use the numbers to
check your optimizations. Zero dependencies, Python 3.10+.

## What it measures

| Metric | How |
|---|---|
| Wall time (median / min / stdev over several runs) | `time.perf_counter` |
| CPU time | `time.process_time` |
| Peak memory and memory kept by the result | `tracemalloc` (separate pass, so it doesn't skew timing) |
| GC load (collections per run) | `gc.get_stats` |
| Where the time goes (per function) | `cProfile` |
| Growth curve + estimated complexity | log-log slope over increasing input sizes |
| Before/after comparison with output check | `compare()` |

## Usage

Command line (works with LeetCode-style `class Solution` too):

```bash
pip install -e .
optipy examples/two_sum.py:Solution.twoSum --args "[[2,7,11,15], 9]" --number 1000 --profile --out results.json
```

Python API:

```python
from optipy import measure, growth, compare, format_result, format_growth

print(format_result(measure(my_func, data)))
print(format_growth(growth(my_func, lambda n: list(range(n)), [1_000, 10_000, 100_000])))
print(compare(slow_version, fast_version, data).speedup)
```

Run `python examples/demo.py` for a full example.

## Notes

- Run each measurement several times; a single number is noisy (OS, load, cache).
- If your function mutates its input (e.g. sorts in place), use `fresh=True`.
- For very fast functions raise `number` so one run lasts long enough to time.
- `process_time` has coarse resolution on Windows (~15 ms), so trust wall time for short functions.
- Peak memory only counts allocations made *inside* the call, not the arguments passed in.
- The growth exponent is an estimate, not a proof of complexity.

## Roadmap

- [x] Measurement: time, CPU, memory, GC, profile, growth
- [x] Before/after comparison with correctness check
- [ ] Line-level time and memory
- [ ] Optimization suggestions (e.g. list -> set, generator instead of list)
- [ ] Automatic report (Markdown/HTML)

## Tests

```bash
pip install pytest
pytest
```
