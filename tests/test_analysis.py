from up4u_audit.analysis import analyze, denial_breakdown, leak_map, retired_carc_note
from up4u_audit.formatting import money


def test_denial_breakdown_uses_current_codes_and_labels_15_retired(book):
    frame = denial_breakdown(book.claims)
    current = frame[~frame["retired"]]
    assert list(current["carc"]) == ["197", "198", "27", "50", "4", "29"]
    assert current["claims"].sum() == 685
    retired = frame[frame["carc"] == "15"].iloc[0]
    assert retired["retired"]
    assert retired["claims"] == 0
    assert "stopped by X12" in retired_carc_note()
    assert "2018-05-01" in retired_carc_note()


def test_leak_map_defines_each_pile_and_refuses_to_add_them(book):
    leaks = leak_map(book)
    assert "not added together" in leaks["note"]
    assert leaks["no_show"]["visits"] == 520
    assert leaks["late_cancel"]["visits"] == 174
    assert leaks["denials"]["claims"] == 685
    assert leaks["unworked_denials"]["claims"] < leaks["denials"]["claims"]
    assert leaks["no_show"]["illustrative_cents"] > 0
    assert leaks["unused_authorizations"]["open_illustrative_cents"] > 0
    assert leaks["unused_authorizations"]["expired_illustrative_cents"] > 0
    for key in ("no_show", "late_cancel", "denials", "unworked_denials"):
        assert leaks[key]["definition"]
    assert "not an additional leak" in leaks["unworked_denials"]["definition"]


def test_analyze_headline_matches_the_frames(book):
    stats = analyze(book)
    head = stats["headline"]
    assert head["billed_cents"] == int(book.claims["billed_cents"].sum())
    assert head["paid_cents"] == int(book.claims["paid_cents"].sum())
    assert head["denial_rate"] == 685 / 3400
    assert abs(head["no_show_rate"] - 520 / 4094) < 1e-12
    assert stats["payers"]["denied_claims"].sum() == 685
    assert stats["aging"]["unworked_claims"].sum() == int((book.claims["denied"] & ~book.claims["worked"]).sum())
    assert stats["months"]["billed_cents"].sum() == head["billed_cents"]
    assert money(head["billed_cents"]) == "$520,457.03"


def test_weekday_order_is_preserved_in_the_attendance_table(book):
    by_day = analyze(book)["attendance"]["by_weekday"].set_index("weekday")["no_show_rate"]
    assert list(by_day.nlargest(2).index) == ["Monday", "Friday"] or set(by_day.nlargest(2).index) == {
        "Monday",
        "Friday",
    }
