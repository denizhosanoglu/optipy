"""Command line: optipy path/to/file.py:function --args '[...]'"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

from .core import format_result, measure, profile_top


def _load(target: str):
    path, _, name = target.rpartition(":")
    if not path or not name:
        raise SystemExit("target format: file.py:function  (or file.py:Class.method)")
    spec = importlib.util.spec_from_file_location("optipy_target", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    obj = module
    for part in name.split("."):
        obj = getattr(obj, part)
        if isinstance(obj, type):      # LeetCode style: class Solution
            obj = obj()
    return obj


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="optipy", description="Measure speed and memory of a Python function.")
    p.add_argument("target", help="file.py:function or file.py:Class.method")
    p.add_argument("--args", default="[]", help="positional arguments as a JSON list")
    p.add_argument("--runs", type=int, default=7)
    p.add_argument("--number", type=int, default=1, help="calls per run (raise for very fast functions)")
    p.add_argument("--fresh", action="store_true", help="deep-copy arguments for every call (if the function mutates them)")
    p.add_argument("--profile", action="store_true", help="also show the top functions from cProfile")
    p.add_argument("--out", help="save the results as JSON to this file")
    ns = p.parse_args(argv)

    func = _load(ns.target)
    args = json.loads(ns.args)
    result = measure(func, *args, runs=ns.runs, number=ns.number, fresh=ns.fresh)
    print(format_result(result))

    payload = {"result": result.to_dict()}
    if ns.profile:
        rows = profile_top(func, *args)
        print("\ncProfile (top by cumulative time):")
        for r in rows:
            print(f"  {r['cumtime_s']:.6f}s  {r['ncalls']:>7} calls  {r['function']}")
        payload["profile"] = rows

    if ns.out:
        Path(ns.out).write_text(json.dumps(payload, indent=2))
        print(f"\nsaved -> {ns.out}")
