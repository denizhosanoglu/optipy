from optipy import compare, growth, measure, profile_top


def build_list(n):
    return [i * i for i in range(n)]


def test_measure_basic():
    r = measure(build_list, 10_000, runs=3)
    assert r.wall_median_s > 0
    assert r.peak_mem_kb > 0
    assert r.net_mem_kb > 0          # the returned list is still alive


def test_fresh_protects_mutation():
    def pop_all(xs):
        while xs:
            xs.pop()
        return 0
    data = list(range(1000))
    measure(pop_all, data, runs=3, fresh=True)
    assert len(data) == 1000


def test_memory_grows_linearly():
    g = growth(build_list, lambda n: n, [20_000, 40_000, 80_000, 160_000], runs=2)
    assert 0.9 < g.mem_exponent < 1.1


def test_compare_detects_speedup_and_equality():
    def slow(n):
        t = 0
        for i in range(n):
            t += i
        return t

    def fast(n):
        return n * (n - 1) // 2

    c = compare(slow, fast, 200_000, runs=3)
    assert c.same_output
    assert c.speedup > 1


def test_profile_top():
    rows = profile_top(build_list, 1000, top=5)
    assert rows and "cumtime_s" in rows[0]
