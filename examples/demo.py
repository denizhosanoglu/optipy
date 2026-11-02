import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from two_sum import Solution

from optipy import compare, format_comparison, format_growth, format_result, growth, measure

s = Solution()
nums = list(range(2000))

print(format_result(measure(s.twoSum, nums, -1)))
print()

# worst case: no answer exists, so both versions scan everything
print(format_comparison(compare(s.twoSumSlow, s.twoSum, nums, -1)))
print()

print(format_growth(growth(lambda n: s.twoSumSlow(n, -1), lambda k: list(range(k)), [250, 500, 1000, 2000])))
print()
print(format_growth(growth(lambda n: s.twoSum(n, -1), lambda k: list(range(k)), [20_000, 40_000, 80_000, 160_000])))
