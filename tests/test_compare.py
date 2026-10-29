from __future__ import annotations

import importlib.util
import sys
import random
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))
spec = importlib.util.spec_from_file_location("compare_outputs", Path(__file__).resolve().parents[1] / "helpers" / "compare_outputs.py")
comparison = importlib.util.module_from_spec(spec)
spec.loader.exec_module(comparison)


class ComparisonTests(unittest.TestCase):
    def test_subtraction_matches_address_sets_with_overlap_and_fragmentation(self) -> None:
        random_source = random.Random(0)
        for _ in range(100):
            left_set = {n for n in range(256) if random_source.randrange(3)}
            right_set = {n for n in range(256) if random_source.randrange(2)}
            left = comparison.merge([(n, n) for n in left_set])
            right = comparison.merge([(n, n) for n in right_set])
            difference = comparison.subtract(left, right)
            self.assertEqual({n for start, end in difference for n in range(start, end + 1)}, left_set - right_set)
            self.assertEqual(comparison.size(difference), len(left_set - right_set))

    def test_subtraction_preserves_ipv6_precision(self) -> None:
        start = 2 ** 120
        self.assertEqual(comparison.subtract([(start, start + 1023)], [(start + 256, start + 511)]),
                         [(start, start + 255), (start + 512, start + 1023)])


if __name__ == "__main__":
    unittest.main()
