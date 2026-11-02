"""optipy core: measure time, CPU, memory and GC load of a callable."""
from __future__ import annotations

import copy
import cProfile
import gc
import math
import os
import pstats
import statistics
import time
import tracemalloc
from dataclasses import asdict, dataclass
from typing import Any, Callable, Sequence


# ----------------------------------------------------------------- data types
@dataclass
class Result:
    name: str
    runs: int
    number: int                  # calls per timed run
    wall_median_s: float         # per call
    wall_min_s: float
    wall_stdev_s: float
    cpu_median_s: float
    peak_mem_kb: float           # peak allocated inside the call (tracemalloc)
    net_mem_kb: float            # memory still held by the return value
    gc_collections_per_run: float

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class GrowthReport:
    name: str
    sizes: list[int]
    times_s: list[float]
    peak_kb: list[float]
    time_exponent: float         # slope of log(time) vs log(n)
    mem_exponent: float
    time_class: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Comparison:
    before: Result
    after: Result
    same_output: bool
    speedup: float               # before_time / after_time
    peak_mem_ratio: float        # after_peak / before_peak

    def to_dict(self) -> dict:
        return {
            "before": self.before.to_dict(),
            "after": self.after.to_dict(),
            "same_output": self.same_output,
            "speedup": self.speedup,
            "peak_mem_ratio": self.peak_mem_ratio,
        }


# -------------------------------------------------------------------- helpers
def _gc_count() -> int:
    return sum(s["collections"] for s in gc.get_stats())


def _batch(args: tuple, kwargs: dict, n: int, fresh: bool) -> list[tuple]:
    """Argument sets for n calls. fresh=True deep-copies them (for functions
    that mutate their input); the copying happens outside the timed region."""
    if not fresh:
        return [(args, kwargs)] * n
    return [(copy.deepcopy(args), copy.deepcopy(kwargs)) for _ in range(n)]


def _exponent(sizes: Sequence[int], values: Sequence[float]) -> float:
    pts = [(math.log(n), math.log(v)) for n, v in zip(sizes, values) if n > 0 and v > 0]
    if len(pts) < 2:
        return float("nan")
    xs, ys = zip(*pts)
    return statistics.linear_regression(xs, ys).slope


def _classify(exp: float) -> str:
    if math.isnan(exp):
        return "unknown"
    if exp <= 0.3:
        return "~O(1) / O(log n)"
    if exp <= 1.25:
        return "~O(n) / O(n log n)"
    if exp <= 1.75:
        return "~O(n^1.5)"
    if exp <= 2.5:
        return "~O(n^2)"
    return "O(n^3) or worse"


def _fmt_time(s: float) -> str:
    if s >= 1:
        return f"{s:.3f} s"
    if s >= 1e-3:
        return f"{s * 1e3:.3f} ms"
    return f"{s * 1e6:.1f} us"


# ------------------------------------------------------------------- measure
def measure(func: Callable, *args, runs: int = 7, number: int = 1,
            warmup: int = 1, fresh: bool = False, **kwargs) -> Result:
    """Measure func(*args, **kwargs).

    runs:   number of timed repetitions (median/min/stdev are reported)
    number: calls per repetition; raise it for very fast functions
    fresh:  deep-copy the arguments for every call (use if func mutates them)

    Time and memory are measured in separate passes, because tracemalloc
    slows the code down.
    """
    for a, k in _batch(args, kwargs, warmup, fresh):
        func(*a, **k)

    wall: list[float] = []
    cpu: list[float] = []
    gc.collect()
    gc_before = _gc_count()
    for _ in range(runs):
        batch = _batch(args, kwargs, number, fresh)
        c0 = time.process_time()
        t0 = time.perf_counter()
        for a, k in batch:
            func(*a, **k)
        wall.append((time.perf_counter() - t0) / number)
        cpu.append((time.process_time() - c0) / number)
    gc_per_run = (_gc_count() - gc_before) / runs

    # memory pass
    a, k = _batch(args, kwargs, 1, fresh)[0]
    gc.collect()
    tracemalloc.start()
    try:
        out = func(*a, **k)
        net, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    del out

    return Result(
        name=getattr(func, "__qualname__", repr(func)),
        runs=runs,
        number=number,
        wall_median_s=statistics.median(wall),
        wall_min_s=min(wall),
        wall_stdev_s=statistics.stdev(wall) if len(wall) > 1 else 0.0,
        cpu_median_s=statistics.median(cpu),
        peak_mem_kb=peak / 1024,
        net_mem_kb=net / 1024,
        gc_collections_per_run=gc_per_run,
    )


# ------------------------------------------------------------------- profile
def profile_top(func: Callable, *args, top: int = 10, **kwargs) -> list[dict]:
    """cProfile the call and return the `top` functions by cumulative time."""
    pr = cProfile.Profile()
    pr.enable()
    try:
        func(*args, **kwargs)
    finally:
        pr.disable()
    stats = pstats.Stats(pr).stats  # type: ignore[attr-defined]
    rows = []
    for (file, line, name), (_cc, ncalls, tottime, cumtime, _callers) in stats.items():
        rows.append({
            "function": f"{name} ({os.path.basename(file)}:{line})",
            "ncalls": ncalls,
            "tottime_s": tottime,
            "cumtime_s": cumtime,
        })
    rows.sort(key=lambda r: r["cumtime_s"], reverse=True)
    return rows[:top]


# -------------------------------------------------------------------- growth
def growth(func: Callable, make_input: Callable[[int], Any], sizes: Sequence[int],
           runs: int = 5, number: int = 1, fresh: bool = False) -> GrowthReport:
    """Run func(make_input(n)) for each n and estimate how time and memory
    grow (slope of the log-log plot)."""
    times, mems = [], []
    for n in sizes:
        r = measure(func, make_input(n), runs=runs, number=number, fresh=fresh)
        times.append(r.wall_median_s)
        mems.append(r.peak_mem_kb)
    t_exp = _exponent(sizes, times)
    return GrowthReport(
        name=getattr(func, "__qualname__", repr(func)),
        sizes=list(sizes),
        times_s=times,
        peak_kb=mems,
        time_exponent=t_exp,
        mem_exponent=_exponent(sizes, mems),
        time_class=_classify(t_exp),
    )


# ------------------------------------------------------------------- compare
def compare(before: Callable, after: Callable, *args, runs: int = 7,
            number: int = 1, fresh: bool = False, **kwargs) -> Comparison:
    """Compare an original function with an optimized one on the same input,
    and check that both return the same output."""
    out_b = before(*copy.deepcopy(args), **copy.deepcopy(kwargs))
    out_a = after(*copy.deepcopy(args), **copy.deepcopy(kwargs))
    rb = measure(before, *args, runs=runs, number=number, fresh=fresh, **kwargs)
    ra = measure(after, *args, runs=runs, number=number, fresh=fresh, **kwargs)
    return Comparison(
        before=rb,
        after=ra,
        same_output=(out_b == out_a),
        speedup=rb.wall_median_s / ra.wall_median_s if ra.wall_median_s else float("inf"),
        peak_mem_ratio=(ra.peak_mem_kb / rb.peak_mem_kb) if rb.peak_mem_kb else float("nan"),
    )


# ---------------------------------------------------------------- formatting
def format_result(r: Result) -> str:
    return "\n".join([
        f"{r.name}  ({r.runs} runs x {r.number} call(s))",
        f"  wall time   median {_fmt_time(r.wall_median_s)}   min {_fmt_time(r.wall_min_s)}   stdev {_fmt_time(r.wall_stdev_s)}",
        f"  cpu time    median {_fmt_time(r.cpu_median_s)}",
        f"  memory      peak {r.peak_mem_kb:.1f} KB   kept by result {r.net_mem_kb:.1f} KB",
        f"  gc          {r.gc_collections_per_run:.2f} collections / run",
    ])


def format_growth(g: GrowthReport) -> str:
    lines = [g.name, f"  {'n':>10}  {'time':>12}  {'peak mem':>12}"]
    for n, t, m in zip(g.sizes, g.times_s, g.peak_kb):
        lines.append(f"  {n:>10}  {_fmt_time(t):>12}  {m:>9.1f} KB")
    lines.append(f"  time exponent {g.time_exponent:.2f} -> {g.time_class}")
    lines.append(f"  memory exponent {g.mem_exponent:.2f}")
    return "\n".join(lines)


def format_comparison(c: Comparison) -> str:
    return "\n".join([
        f"before: {c.before.name}  {_fmt_time(c.before.wall_median_s)}  peak {c.before.peak_mem_kb:.1f} KB",
        f"after:  {c.after.name}  {_fmt_time(c.after.wall_median_s)}  peak {c.after.peak_mem_kb:.1f} KB",
        f"speedup x{c.speedup:.2f}   peak memory ratio {c.peak_mem_ratio:.2f}   same output: {c.same_output}",
    ])
