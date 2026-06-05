import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from utils.statistics import normalized_least_squares_slope


class TestStatistics(unittest.TestCase):
    def test_normalized_least_squares_slope_matches_linear_change(self):
        data = np.array([2.0, 4.0, 6.0, 8.0])

        self.assertAlmostEqual(normalized_least_squares_slope(data), 6.0)

    def test_normalized_least_squares_slope_normalizes_position_ends(self):
        data = np.array([5.0, 9.0])
        positions = np.array([10.0, 30.0])

        self.assertAlmostEqual(
            normalized_least_squares_slope(data, positions), 4.0)

    def test_normalized_least_squares_slope_uses_least_squares_fit(self):
        data = np.array([0.0, 0.0, 3.0, 3.0])

        self.assertAlmostEqual(normalized_least_squares_slope(data), 3.6)

    def test_normalized_least_squares_slope_handles_short_data(self):
        self.assertEqual(normalized_least_squares_slope([42.0]), 0.0)


if __name__ == "__main__":
    unittest.main()
