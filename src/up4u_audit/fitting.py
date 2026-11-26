"""Small integer-allocation helpers.

The generator has to hit published row and column totals at the same time
(payers and months, weekdays and clinicians). These functions do that and
nothing more statistical.
"""

from __future__ import annotations

import numpy as np


def largest_remainder(weights: list[float] | np.ndarray, total: int) -> list[int]:
    """Nonnegative integers that sum to ``total`` and follow ``weights``."""
    total = int(total)
    arr = np.asarray(weights, dtype=float)
    if total < 0:
        raise ValueError("total must be nonnegative")
    if arr.ndim != 1 or len(arr) == 0:
        raise ValueError("weights must be a non-empty 1-d sequence")
    if np.any(arr < 0):
        raise ValueError("weights must be nonnegative")
    if total == 0:
        return [0] * len(arr)
    if float(arr.sum()) <= 0:
        raise ValueError("weights sum to zero")
    raw = arr / arr.sum() * total
    base = np.floor(raw + 1e-9).astype(int)
    left = total - int(base.sum())
    frac = raw - base
    order = np.argsort(-frac, kind="mergesort")
    for k in range(left):
        base[order[k % len(base)]] += 1
    return [int(v) for v in base]


def shift_to_caps(counts: list[int], caps: list[int]) -> list[int]:
    """Move units off entries that exceed ``caps``, preserving the sum."""
    values = [int(v) for v in counts]
    limits = [int(v) for v in caps]
    if len(values) != len(limits):
        raise ValueError("counts and caps differ in length")
    if sum(values) > sum(limits):
        raise ValueError("caps cannot hold the total")
    guard = 0
    while True:
        over = [i for i, value in enumerate(values) if value > limits[i]]
        if not over:
            return values
        i = over[0]
        extra = values[i] - limits[i]
        receivers = [j for j, value in enumerate(values) if value < limits[j]]
        if not receivers:
            raise ValueError("no room to move excess")
        # Prefer the receiver with the most room.
        j = max(receivers, key=lambda idx: limits[idx] - values[idx])
        step = min(extra, limits[j] - values[j])
        values[i] -= step
        values[j] += step
        guard += 1
        if guard > sum(limits) + 5:
            raise RuntimeError("cap shift did not finish")


def integer_matrix(
    row_targets: list[int],
    col_targets: list[int],
    weights: np.ndarray | None = None,
) -> np.ndarray:
    """Nonnegative integer matrix with the given margins.

    ``weights`` steer the interior. Zeros are allowed in the result. The
    routine is meant for modest tables (payers by month, days by clinician),
    including cent-valued dollar tables whose rounding residue is small.
    """
    rows = [int(v) for v in row_targets]
    cols = [int(v) for v in col_targets]
    if sum(rows) != sum(cols):
        raise ValueError(f"margins differ: {sum(rows)} vs {sum(cols)}")
    n_rows, n_cols = len(rows), len(cols)
    if weights is None:
        weights = np.ones((n_rows, n_cols), dtype=float)
    matrix = np.array(weights, dtype=float)
    if matrix.shape != (n_rows, n_cols):
        raise ValueError("weights have the wrong shape")
    if np.any(matrix < 0):
        raise ValueError("weights must be nonnegative")
    matrix = np.where(matrix == 0, 1e-12, matrix)

    row_arr = np.asarray(rows, dtype=float)
    col_arr = np.asarray(cols, dtype=float)
    fitted = matrix * np.outer(row_arr, col_arr) / max(float(row_arr.sum()), 1.0)
    for _ in range(80):
        row_sum = fitted.sum(axis=1)
        row_sum = np.where(row_sum == 0, 1.0, row_sum)
        fitted *= (row_arr / row_sum)[:, None]
        col_sum = fitted.sum(axis=0)
        col_sum = np.where(col_sum == 0, 1.0, col_sum)
        fitted *= (col_arr / col_sum)[None, :]

    floored = np.floor(fitted + 1e-8).astype(int)
    floored = np.maximum(floored, 0)
    frac = fitted - np.floor(fitted + 1e-8)
    for i, target in enumerate(rows):
        diff = target - int(floored[i].sum())
        if diff > 0:
            order = np.argsort(-frac[i], kind="mergesort")
            for k in range(diff):
                floored[i, order[k % n_cols]] += 1
        elif diff < 0:
            order = np.argsort(frac[i], kind="mergesort")
            k = 0
            while diff < 0 and k < n_cols * (abs(diff) + 2):
                j = int(order[k % n_cols])
                if floored[i, j] > 0:
                    floored[i, j] -= 1
                    diff += 1
                k += 1
        if int(floored[i].sum()) != target:
            raise RuntimeError(f"could not match row {i}")

    # Column repair preserves each row sum by moving mass across a row.
    guard = 0
    limit = n_rows * n_cols * 50 + 1000
    while True:
        diff = np.asarray(cols) - floored.sum(axis=0)
        if np.all(diff == 0):
            return floored
        over = int(np.argmin(diff))
        under = int(np.argmax(diff))
        if diff[over] >= 0 or diff[under] <= 0:
            raise RuntimeError("column repair lost the sign of the gap")
        need = int(min(-diff[over], diff[under]))
        moved = False
        for i in range(n_rows):
            available = int(floored[i, over])
            if available <= 0:
                continue
            step = min(available, need)
            floored[i, over] -= step
            floored[i, under] += step
            moved = True
            break
        if not moved:
            raise RuntimeError("column repair stuck")
        guard += 1
        if guard > limit:
            raise RuntimeError("column repair took too many steps")


def split_exact(total: int, count: int, low: int, high: int, rng: np.random.Generator) -> np.ndarray:
    """``count`` integers in ``[low, high]`` that sum to ``total``."""
    total, count, low, high = int(total), int(count), int(low), int(high)
    if count <= 0:
        raise ValueError("count must be positive")
    if low > high:
        raise ValueError("low exceeds high")
    if not count * low <= total <= count * high:
        raise ValueError(f"{total} is outside [{count * low}, {count * high}]")
    if count == 1:
        return np.array([total], dtype=int)

    remaining = total - count * low
    room = high - low
    # Draw across the whole allowed band, then nudge onto the required sum.
    # A narrow weight around the mean would hide the spread in the sample claims.
    proposal = rng.uniform(low, high, size=count)
    for _ in range(24):
        gap = total - float(proposal.sum())
        if abs(gap) < 1e-6:
            break
        slack = (high - proposal) if gap > 0 else (proposal - low)
        if float(slack.sum()) <= 0:
            break
        proposal = np.clip(proposal + gap * slack / slack.sum(), low, high)
    raw = proposal - low
    extra = np.floor(raw + 1e-9).astype(int)
    left = remaining - int(extra.sum())
    if left > 0:
        order = np.argsort(-(raw - extra), kind="mergesort")
        for k in range(left):
            extra[int(order[k % count])] += 1
    elif left < 0:
        order = np.argsort(raw - extra, kind="mergesort")
        k = 0
        while left < 0 and k < count * (abs(left) + 2):
            j = int(order[k % count])
            if extra[j] > 0:
                extra[j] -= 1
                left += 1
            k += 1

    # Largest-remainder can overshoot a cap by a unit or two. Walk it back.
    guard = 0
    while int(extra.max()) > room:
        donor = int(np.argmax(extra))
        receivers = np.where(extra < room)[0]
        if len(receivers) == 0:
            raise RuntimeError("split cannot honor the cap")
        receiver = int(receivers[np.argmin(extra[receivers])])
        extra[donor] -= 1
        extra[receiver] += 1
        guard += 1
        if guard > count * room:
            raise RuntimeError("split cap repair did not finish")

    out = extra + low
    if int(out.sum()) != total or int(out.min()) < low or int(out.max()) > high:
        raise RuntimeError("split_exact failed its own check")
    return out.astype(int)
