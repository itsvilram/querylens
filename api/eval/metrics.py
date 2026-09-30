"""How we score and compare runs. Pure functions.

Execution accuracy (EX) is BIRD's official rule: the predicted query is right
when set(predicted rows) == set(gold rows). Row order and duplicate rows are
ignored; column order counts (rows are compared as tuples).
"""

import math
from collections.abc import Sequence

type Row = tuple[object, ...]


def execution_match(predicted: Sequence[Row], gold: Sequence[Row]) -> bool:
    """BIRD's official EX: same set of rows."""
    return set(predicted) == set(gold)


def strict_match(predicted: Sequence[Row], gold: Sequence[Row]) -> bool:
    """Stricter: same rows, same order, same duplicates."""
    return list(predicted) == list(gold)


def wilson_interval(correct: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """95% confidence interval for an accuracy, as fractions (Wilson score).

    Better than "p ± 1.96·sqrt(p(1-p)/n)" for small n or p near 0 or 1.
    """
    if total == 0:
        return (0.0, 0.0)
    p = correct / total
    centre = (p + z * z / (2 * total)) / (1 + z * z / total)
    spread = (z / (1 + z * z / total)) * math.sqrt(
        p * (1 - p) / total + z * z / (4 * total * total)
    )
    return (max(0.0, centre - spread), min(1.0, centre + spread))


def paired_comparison(before: Sequence[bool], after: Sequence[bool]) -> tuple[int, int, float]:
    """Compare two configs on the same questions.

    Returns (fixed, broken, p_value): questions that went wrong → right, right →
    wrong, and the exact two-sided McNemar p-value. Only the questions that
    changed carry information; if fixed and broken are close, p is large and
    the difference is likely noise.
    """
    if len(before) != len(after):
        raise ValueError("Both runs must cover the same questions.")
    fixed = sum(1 for b, a in zip(before, after, strict=True) if not b and a)
    broken = sum(1 for b, a in zip(before, after, strict=True) if b and not a)
    changed = fixed + broken
    if changed == 0:
        return (0, 0, 1.0)
    tail = sum(math.comb(changed, k) for k in range(min(fixed, broken) + 1)) / 2**changed
    return (fixed, broken, min(1.0, 2 * tail))


def percentile(values: Sequence[float], q: float) -> float:
    """The q-th percentile (0-100) with linear interpolation."""
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * q / 100
    low, high = math.floor(position), math.ceil(position)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)
