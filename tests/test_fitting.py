import numpy as np

from up4u_audit.fitting import integer_matrix, largest_remainder, shift_to_caps, split_exact


def test_largest_remainder_hits_the_total_and_prefers_larger_weights():
    counts = largest_remainder([1, 1, 2], 10)
    assert sum(counts) == 10
    assert counts[2] > counts[0]


def test_shift_to_caps_preserves_the_sum():
    moved = shift_to_caps([8, 1, 1], [3, 5, 5])
    assert moved == [3, 5, 2] or sum(moved) == 10
    assert sum(moved) == 10
    assert all(value <= cap for value, cap in zip(moved, [3, 5, 5]))


def test_integer_matrix_matches_both_margins():
    matrix = integer_matrix([10, 5, 5], [8, 7, 5])
    assert matrix.sum(axis=1).tolist() == [10, 5, 5]
    assert matrix.sum(axis=0).tolist() == [8, 7, 5]
    assert (matrix >= 0).all()


def test_split_exact_stays_inside_the_band():
    rng = np.random.default_rng(3)
    parts = split_exact(10_000, 8, 650, 2_400, rng)
    assert int(parts.sum()) == 10_000
    assert int(parts.min()) >= 650
    assert int(parts.max()) <= 2_400
