"""Small, dependency-free statistics for benchmark reports."""

from __future__ import annotations

import math
import random
from collections.abc import Callable, Sequence


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    """95% Wilson score interval for a binomial proportion."""
    if n == 0:
        return None
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def percentile(values: Sequence[float], pct: float) -> float | None:
    """Nearest-rank percentile."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(1, math.ceil(pct / 100 * len(ordered))) - 1]


def paired_bootstrap(
    pairs: Sequence[tuple[float, float]],
    statistic: Callable[[Sequence[tuple[float, float]]], float | None],
    *,
    resamples: int,
    seed: int,
) -> tuple[float, float] | None:
    """95% percentile bootstrap CI of `statistic` over case-paired observations."""
    if len(pairs) < 2:
        return None
    rng = random.Random(seed)  # noqa: S311 - reproducible resampling, not security
    n = len(pairs)
    values: list[float] = []
    for _ in range(resamples):
        sample = [pairs[rng.randrange(n)] for _ in range(n)]
        value = statistic(sample)
        if value is not None:
            values.append(value)
    if not values:
        return None
    values.sort()
    return values[int(0.025 * (len(values) - 1))], values[int(0.975 * (len(values) - 1))]


def mean_difference(sample: Sequence[tuple[float, float]]) -> float:
    return sum(b - a for a, b in sample) / len(sample)
