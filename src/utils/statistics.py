import numpy as np


def normalized_least_squares_slope(data, positions=None):
    """Return the least-squares slope after normalizing x endpoints to 0 and 1."""
    values = np.asarray(data, dtype=float).reshape(-1)

    if len(values) < 2:
        return 0.0

    if positions is None:
        x = np.linspace(0.0, 1.0, len(values))
    else:
        x = np.asarray(positions, dtype=float).reshape(-1)
        if len(x) != len(values):
            raise ValueError("positions must have the same length as data")
        x_range = x[-1] - x[0]
        if x_range == 0:
            return 0.0
        x = (x - x[0]) / x_range

    x_offset = x - x.mean()
    y_offset = values - values.mean()
    denominator = np.sum(x_offset ** 2)

    if denominator == 0:
        return 0.0

    return float(np.sum(x_offset * y_offset) / denominator)
