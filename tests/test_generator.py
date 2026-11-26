import pandas as pd

from up4u_audit.carc import CARC_CATALOG
from up4u_audit.generator import generate
from up4u_audit.targets import (
    CLINICIANS,
    KEPT_VISITS,
    MONTHS,
    PAYERS,
    SOURCE_DAYS,
    WORKBOOK_CO15_DENIALS,
    cents,
)


def test_same_seed_is_the_same_book(book):
    again = generate(7)
    pd.testing.assert_frame_equal(book.claims, again.claims)
    pd.testing.assert_frame_equal(book.appointments, again.appointments)
    pd.testing.assert_frame_equal(book.authorizations, again.authorizations)


def test_a_different_seed_changes_the_book(book):
    other = generate(8)
    assert not book.claims["billed_cents"].equals(other.claims["billed_cents"])


def test_claim_totals_match_the_workbook(book):
    claims = book.claims
    assert len(claims) == KEPT_VISITS == 3400
    assert int(claims["billed_cents"].sum()) == cents("520457.03")
    assert int(claims["paid_cents"].sum()) == cents("281231.16")
    assert int(claims["denied"].sum()) == 685
    assert round(claims["denied"].mean(), 3) == 0.201


def test_payer_and_month_dollars_match(book):
    claims = book.claims
    for payer in PAYERS:
        part = claims[claims["payer"] == payer.name]
        assert len(part) == payer.claims
        assert int(part["billed_cents"].sum()) == payer.billed_cents
        assert int(part["paid_cents"].sum()) == payer.paid_cents
        assert int(part["denied"].sum()) == payer.denials
    for month in MONTHS:
        part = claims[claims["month"] == month.month]
        assert int(part["billed_cents"].sum()) == month.billed_cents
        assert int(part["paid_cents"].sum()) == month.paid_cents


def test_active_carc_counts_and_retired_code_is_absent(book):
    denied = book.claims[book.claims["denied"]]
    counts = denied["carc"].value_counts().to_dict()
    assert counts == {"197": 118, "198": 88, "27": 203, "50": 109, "4": 100, "29": 67}
    assert counts["197"] + counts["198"] == WORKBOOK_CO15_DENIALS
    assert "15" not in counts
    assert CARC_CATALOG["4"].description == "The procedure code is inconsistent with the modifier used."
    assert CARC_CATALOG["15"].retired
    assert CARC_CATALOG["15"].stop_date.isoformat() == "2018-05-01"
    assert CARC_CATALOG["197"].description.startswith("Precertification/authorization/notification")
    assert CARC_CATALOG["198"].description.startswith("Precertification/notification/authorization")


def test_denied_claims_pay_nothing_and_charges_stay_in_band(book):
    claims = book.claims
    denied = claims[claims["denied"]]
    clean = claims[~claims["denied"]]
    assert int(denied["paid_cents"].sum()) == 0
    assert int(denied["allowed_cents"].sum()) == 0
    assert (denied["denial_group"] == "CO").all()
    assert (clean["paid_cents"] <= clean["allowed_cents"]).all()
    assert (clean["allowed_cents"] <= clean["billed_cents"]).all()
    assert claims["billed_cents"].min() >= 65_00
    assert claims["billed_cents"].max() <= 240_00
    assert claims["billed_cents"].std() > 40_00


def test_attendance_keeps_the_workbook_pattern(book):
    appointments = book.appointments
    assert len(appointments) == 4094
    assert int((appointments["status"] == "no_show").sum()) == 520
    assert int((appointments["status"] == "late_cancel").sum()) == 174
    assert int((appointments["status"] == "kept").sum()) == 3400
    assert round((appointments["status"] == "no_show").mean(), 3) == 0.127

    by_day = appointments.groupby("weekday")["status"].apply(lambda s: (s == "no_show").mean())
    source_day = {day.weekday: day.no_shows / day.appointments for day in SOURCE_DAYS}
    for weekday, rate in source_day.items():
        assert abs(by_day[weekday] - rate) < 0.005
    assert by_day["Monday"] > by_day["Wednesday"]
    assert by_day["Friday"] > by_day["Tuesday"]

    by_clinician = appointments.groupby("clinician")["status"].apply(lambda s: (s == "no_show").mean())
    source_clinician = {c.name: c.no_shows / c.appointments for c in CLINICIANS}
    for name, rate in source_clinician.items():
        assert abs(by_clinician[name] - rate) < 0.005
    assert by_clinician["D. Ortiz, PT"] == by_clinician.min()


def test_clinicians_bill_their_own_service_line(book):
    claims = book.claims
    assert set(claims.loc[claims["service_line"] == "SLP", "cpt"]) == {"92507"}
    assert set(claims.loc[claims["service_line"] == "OT", "cpt"]) == {"97535"}
    assert set(claims.loc[claims["service_line"] == "PT", "cpt"]) == {"97110"}
    assert set(claims.loc[claims["service_line"] == "ABA", "cpt"]) <= {"97151", "97153", "97155", "97156"}
    assert set(claims.loc[claims["clinician"] == "L. Brooks, RBT", "cpt"]) == {"97153"}


def test_every_kept_visit_has_one_claim(book):
    kept = set(book.appointments.loc[book.appointments["status"] == "kept", "appointment_id"])
    assert kept == set(book.claims["appointment_id"])
    assert book.claims["appointment_id"].is_unique
    assert book.claims["claim_id"].is_unique


def test_authorization_identities(book):
    auths = book.authorizations
    claims = book.claims
    plain = auths[auths["exceeded_units"] == 0]
    exceeded = auths[auths["exceeded_units"] > 0]
    assert (
        plain["used_units"] + plain["missed_units"] + plain["unbooked_units"] == plain["authorized_units"]
    ).all()
    assert (plain["used_units"] <= plain["authorized_units"]).all()
    assert (exceeded["used_units"] == exceeded["authorized_units"] + exceeded["exceeded_units"]).all()
    assert int(claims.loc[claims["carc"] == "198", "units"].sum()) == int(auths["exceeded_units"].sum())
    assert claims.loc[claims["carc"] == "197", "auth_id"].isna().all()
    assert claims.loc[claims["carc"] == "198", "auth_id"].notna().all()
    assert set(auths["status"]) <= {"open", "expired"}
    assert (auths["status"] == "open").any()
    assert (auths["status"] == "expired").any()
    assert int(auths["unbooked_units"].sum()) > 0


def test_patients_are_ids_only(book):
    patients = book.patients
    assert list(patients.columns) == [
        "patient_id",
        "service_line",
        "payer",
        "payer_category",
        "clinician",
    ]
    assert patients["patient_id"].str.fullmatch(r"SC-\d{3}").all()
    forbidden = {"name", "dob", "ssn", "address", "phone", "member_id", "diagnosis"}
    assert forbidden.isdisjoint(patients.columns)
    assert "Medi-Cal (State Plan)" in set(book.claims["payer"])
    assert set(book.claims["service_line"]) == {"ABA", "SLP", "OT", "PT"}


def test_unworked_denials_are_a_subset_and_include_aged_claims(book):
    claims = book.claims
    denied = claims[claims["denied"]]
    assert (~claims.loc[~claims["denied"], "worked"]).sum() == 0
    unworked = denied[~denied["worked"]]
    assert 0 < len(unworked) < len(denied)
    assert (unworked["age_days"] >= 91).any()
    assert (unworked["age_days"] <= 30).any()
