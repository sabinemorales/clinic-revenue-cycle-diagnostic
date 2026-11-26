import pytest

from up4u_audit.plan import weekly_actions
from up4u_audit.roi import CAVEAT, RoiAssumptions, estimate_roi, zeroed_assumptions


def test_zero_rates_produce_zero_illustrative_dollars(book):
    estimate = estimate_roi(book, zeroed_assumptions())
    assert estimate["one_time"]["total_cents"] == 0
    assert estimate["annualized"]["total_cents"] == 0
    assert estimate["audit_fee_cents"] == 120_000


def test_model_states_that_it_is_not_a_promise(book):
    estimate = estimate_roi(book)
    assert estimate["caveat"] == CAVEAT
    assert "not a promise" in estimate["caveat"]
    assert "payback period" in estimate["caveat"]
    assert estimate["one_time"]["low_cents"] < estimate["one_time"]["total_cents"]
    assert estimate["annualized"]["low_cents"] < estimate["annualized"]["total_cents"]
    assert estimate["one_time"]["low_cents"] == pytest.approx(estimate["one_time"]["total_cents"] / 2, rel=0.02)


def test_rework_cannot_exceed_denied_expected_collection(book):
    estimate = estimate_roi(book)
    denied_billed = int(book.claims.loc[book.claims["denied"], "billed_cents"].sum())
    ceiling = denied_billed * estimate["clean_yield"]
    assert estimate["one_time"]["denial_rework_cents"] <= ceiling + 1
    # Unbooked fill is the only other one-time piece, and it is not denial rework.
    assert estimate["one_time"]["total_cents"] == (
        estimate["one_time"]["denial_rework_cents"] + estimate["one_time"]["open_unbooked_fill_cents"]
    )


def test_a_higher_modifier_yield_raises_only_that_code(book):
    base = estimate_roi(book)
    higher = estimate_roi(book, RoiAssumptions(rework_yield_4=0.9))
    base_row = {row["carc"]: row for row in base["by_carc"]}
    higher_row = {row["carc"]: row for row in higher["by_carc"]}
    assert higher_row["4"]["rework_cents"] > base_row["4"]["rework_cents"]
    assert higher_row["29"]["rework_cents"] == base_row["29"]["rework_cents"]


def test_a_longer_window_does_not_shrink_rework(book):
    short = estimate_roi(book, RoiAssumptions(appeal_window_days=30))
    long = estimate_roi(book, RoiAssumptions(appeal_window_days=365))
    assert long["one_time"]["denial_rework_cents"] >= short["one_time"]["denial_rework_cents"]


def test_assumptions_reject_a_yield_above_one():
    with pytest.raises(ValueError):
        RoiAssumptions(rework_yield_4=1.2)


def test_action_plan_uses_the_book_and_does_not_promise_a_week_of_payback(book):
    actions = weekly_actions(book)
    assert [item["week"] for item in actions] == [1, 2, 3, 4]
    text = " ".join(line for item in actions for line in item["lines"])
    assert "CO-4" in text
    assert "CO-197" in text
    assert "CO-198" in text
    assert "CO-27" in text
    assert "CO-29" in text
    assert "Medi-Cal (State Plan)" in text
    assert "Monday" in text and "Friday" in text
    assert "assumptions, not a result" in text
    assert "1-3 weeks" not in text
    assert "payback" not in text.lower()
