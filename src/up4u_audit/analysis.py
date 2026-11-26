"""Describe the synthetic book without turning findings into promises.

Gross leak dollars answer "how big is this pile?" They are not added together:
a missed visit can also be unused authorization time, and an unworked denial
is already inside the denial total.
"""

from __future__ import annotations

import pandas as pd

from up4u_audit.carc import CARC_CATALOG, DISPLAY_ORDER, get_carc
from up4u_audit.formatting import hours_from_units
from up4u_audit.generator import AuditBook
from up4u_audit.targets import WEEKDAYS

LEAKS_ARE_NOT_ADDITIVE = (
    "These rows are different kinds of dollars, and a missed visit can also "
    "sit in unused authorization time. They are not added together."
)

AGE_BUCKETS = ("0-30", "31-60", "61-90", "91+")


def analyze(book: AuditBook) -> dict:
    claims = book.claims
    appointments = book.appointments
    auths = book.authorizations
    clean_yield = _clean_yield(claims)
    paid_per_unit = _paid_per_unit_cents(claims)
    return {
        "headline": headline(book),
        "denials": denial_breakdown(claims),
        "payers": payer_summary(claims),
        "attendance": attendance_summary(appointments),
        "authorizations": authorization_summary(auths),
        "aging": aging_summary(claims),
        "months": monthly_summary(claims),
        "clean_yield": clean_yield,
        "paid_per_unit_cents": paid_per_unit,
        "leaks": leak_map(book, clean_yield, paid_per_unit),
    }


def headline(book: AuditBook) -> dict:
    claims = book.claims
    appointments = book.appointments
    billed = int(claims["billed_cents"].sum())
    paid = int(claims["paid_cents"].sum())
    denied = int(claims["denied"].sum())
    no_shows = int((appointments["status"] == "no_show").sum())
    late = int((appointments["status"] == "late_cancel").sum())
    scheduled = len(appointments)
    return {
        "claims": len(claims),
        "billed_cents": billed,
        "paid_cents": paid,
        "denied_claims": denied,
        "denial_rate": denied / len(claims),
        "collection_rate": paid / billed,
        "scheduled_appointments": scheduled,
        "no_shows": no_shows,
        "late_cancels": late,
        "kept_visits": int((appointments["status"] == "kept").sum()),
        "no_show_rate": no_shows / scheduled,
        "late_cancel_rate": late / scheduled,
        "patients": len(book.patients),
        "authorizations": len(book.authorizations),
        "seed": book.seed,
        "snapshot": book.snapshot,
    }


def denial_breakdown(claims: pd.DataFrame) -> pd.DataFrame:
    denied = claims[claims["denied"]].copy()
    total = len(denied)
    rows = []
    for code in DISPLAY_ORDER:
        part = denied[denied["carc"] == code]
        info = get_carc(code)
        billed = int(part["billed_cents"].sum())
        rows.append(
            {
                "carc": code,
                "code": info.display_code,
                "short_label": info.short_label,
                "description": info.description,
                "retired": info.retired,
                "claims": len(part),
                "share_of_denials": (len(part) / total) if total else 0.0,
                "billed_cents": billed,
            }
        )
        retired = get_carc("15")
        retired_claims = int((denied["carc"] == "15").sum()) if total else 0
        rows.append(
            {
                "carc": "15",
                "code": retired.display_code,
                "short_label": retired.short_label,
                "description": retired.description,
                "retired": True,
                "claims": retired_claims,
                "share_of_denials": (retired_claims / total) if total else 0.0,
                "billed_cents": int(denied.loc[denied["carc"] == "15", "billed_cents"].sum()) if total else 0,
            }
        )
    return pd.DataFrame(rows)


def payer_summary(claims: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for payer, part in claims.groupby("payer", sort=False):
        denied = int(part["denied"].sum())
        rows.append(
            {
                "payer": payer,
                "payer_category": part["payer_category"].iloc[0],
                "claims": len(part),
                "billed_cents": int(part["billed_cents"].sum()),
                "paid_cents": int(part["paid_cents"].sum()),
                "denied_claims": denied,
                "denial_rate": denied / len(part),
            }
        )
    frame = pd.DataFrame(rows)
    return frame.sort_values(["denial_rate", "payer"], ascending=[False, True]).reset_index(drop=True)


def attendance_summary(appointments: pd.DataFrame) -> dict:
    return {
        "by_weekday": _attendance_table(appointments, "weekday", list(WEEKDAYS)),
        "by_clinician": _attendance_table(
            appointments,
            "clinician",
            sorted(appointments["clinician"].unique()),
        ),
        "by_service_line": _attendance_table(
            appointments,
            "service_line",
            ["ABA", "SLP", "OT", "PT"],
        ),
    }


def _attendance_table(appointments: pd.DataFrame, column: str, order: list[str]) -> pd.DataFrame:
    rows = []
    for key in order:
        part = appointments[appointments[column] == key]
        if part.empty:
            continue
        scheduled = len(part)
        no_shows = int((part["status"] == "no_show").sum())
        late = int((part["status"] == "late_cancel").sum())
        rows.append(
            {
                column: key,
                "appointments": scheduled,
                "no_shows": no_shows,
                "late_cancels": late,
                "kept": int((part["status"] == "kept").sum()),
                "no_show_rate": no_shows / scheduled,
                "late_cancel_rate": late / scheduled,
                "no_show_units": int(part.loc[part["status"] == "no_show", "units"].sum()),
                "late_cancel_units": int(part.loc[part["status"] == "late_cancel", "units"].sum()),
            }
        )
    return pd.DataFrame(rows)


def authorization_summary(authorizations: pd.DataFrame) -> dict:
    frame = authorizations.copy()
    frame["unused_units"] = (frame["authorized_units"] - frame["used_units"]).clip(lower=0)
    rows = []
    for service_line in ["ABA", "SLP", "OT", "PT"]:
        part = frame[frame["service_line"] == service_line]
        rows.append(_auth_metrics(service_line, part))
    totals = _auth_metrics("All", frame)
    return {"by_service_line": pd.DataFrame(rows), "totals": totals}


def _auth_metrics(label: str, part: pd.DataFrame) -> dict:
    open_rows = part[part["status"] == "open"]
    expired = part[part["status"] == "expired"]
    unused = int((part["authorized_units"] - part["used_units"]).clip(lower=0).sum())
    open_unused = int((open_rows["authorized_units"] - open_rows["used_units"]).clip(lower=0).sum())
    expired_unused = int((expired["authorized_units"] - expired["used_units"]).clip(lower=0).sum())
    return {
        "service_line": label,
        "authorizations": len(part),
        "authorized_units": int(part["authorized_units"].sum()),
        "used_units": int(part["used_units"].sum()),
        "unused_units": unused,
        "missed_units": int(part["missed_units"].sum()),
        "unbooked_units": int(part["unbooked_units"].sum()),
        "exceeded_units": int(part["exceeded_units"].sum()),
        "open_unused_units": open_unused,
        "expired_unused_units": expired_unused,
        "open_unbooked_units": int(open_rows["unbooked_units"].sum()),
        "authorized_hours": hours_from_units(part["authorized_units"].sum()),
        "unused_hours": hours_from_units(unused),
        "unbooked_hours": hours_from_units(part["unbooked_units"].sum()),
        "open_unused_hours": hours_from_units(open_unused),
        "expired_unused_hours": hours_from_units(expired_unused),
    }


def aging_summary(claims: pd.DataFrame) -> pd.DataFrame:
    denied = claims[claims["denied"]].copy()
    denied["bucket"] = denied["age_days"].map(_age_bucket)
    rows = []
    for bucket in AGE_BUCKETS:
        part = denied[denied["bucket"] == bucket]
        unworked = part[~part["worked"]]
        rows.append(
            {
                "bucket": bucket,
                "denied_claims": len(part),
                "denied_billed_cents": int(part["billed_cents"].sum()),
                "unworked_claims": len(unworked),
                "unworked_billed_cents": int(unworked["billed_cents"].sum()),
            }
        )
    return pd.DataFrame(rows)


def monthly_summary(claims: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for month, part in claims.groupby("month", sort=True):
        billed = int(part["billed_cents"].sum())
        paid = int(part["paid_cents"].sum())
        rows.append(
            {
                "month": month,
                "claims": len(part),
                "billed_cents": billed,
                "paid_cents": paid,
                "collection_rate": paid / billed if billed else 0.0,
                "denied_claims": int(part["denied"].sum()),
            }
        )
    return pd.DataFrame(rows)


def leak_map(book: AuditBook, clean_yield: float | None = None, paid_per_unit: float | None = None) -> dict:
    claims = book.claims
    appointments = book.appointments
    auths = book.authorizations
    if clean_yield is None:
        clean_yield = _clean_yield(claims)
    if paid_per_unit is None:
        paid_per_unit = _paid_per_unit_cents(claims)

    no_show_units = int(appointments.loc[appointments["status"] == "no_show", "units"].sum())
    late_units = int(appointments.loc[appointments["status"] == "late_cancel", "units"].sum())
    denied = claims[claims["denied"]]
    denied_billed = int(denied["billed_cents"].sum())
    unworked = denied[~denied["worked"]]

    open_rows = auths[auths["status"] == "open"]
    expired = auths[auths["status"] == "expired"]
    open_unused_units = int((open_rows["authorized_units"] - open_rows["used_units"]).clip(lower=0).sum())
    expired_unused_units = int((expired["authorized_units"] - expired["used_units"]).clip(lower=0).sum())
    missed_units = int(auths.loc[auths["exceeded_units"] == 0, "missed_units"].sum())
    unbooked_units = int(auths["unbooked_units"].sum())

    return {
        "clean_yield": clean_yield,
        "paid_per_unit_cents": paid_per_unit,
        "note": LEAKS_ARE_NOT_ADDITIVE,
        "no_show": {
            "visits": int((appointments["status"] == "no_show").sum()),
            "units": no_show_units,
            "illustrative_cents": int(round(no_show_units * paid_per_unit)),
            "definition": (
                "No-show units valued at this book's average paid amount per paid unit. "
                "That is scheduled capacity that was not delivered, not cash sitting in accounts receivable."
            ),
        },
        "late_cancel": {
            "visits": int((appointments["status"] == "late_cancel").sum()),
            "units": late_units,
            "illustrative_cents": int(round(late_units * paid_per_unit)),
            "definition": (
                "Late-cancel units valued the same way. The slot was not delivered and, "
                "in this book, the unit was not billed."
            ),
        },
        "denials": {
            "claims": len(denied),
            "billed_cents": denied_billed,
            "expected_collection_cents": int(round(denied_billed * clean_yield)),
            "definition": (
                "Denied billed charges, and those charges multiplied by this book's clean-claim yield "
                "(paid divided by billed on claims that were not denied). The second figure is collection "
                "the denial kept from looking like a clean claim. It is not an amount the audit recovers."
            ),
        },
        "unworked_denials": {
            "claims": len(unworked),
            "billed_cents": int(unworked["billed_cents"].sum()),
            "definition": (
                "Denied claims with no rework recorded. This is a subset of the denial row, not an additional leak."
            ),
        },
        "unused_authorizations": {
            "open_unused_units": open_unused_units,
            "expired_unused_units": expired_unused_units,
            "missed_units_inside_unused": missed_units,
            "unbooked_units": unbooked_units,
            "open_illustrative_cents": int(round(open_unused_units * paid_per_unit)),
            "expired_illustrative_cents": int(round(expired_unused_units * paid_per_unit)),
            "definition": (
                "Authorized units that were not billed, valued at the same paid-per-unit rate. "
                "Missed visits are included here and also in the no-show and late-cancel rows. "
                "Hours never put on the schedule are the unbooked portion. "
                "Expired unused units are shown because they already lapsed. "
                "Authorizations that were exceeded are counted with CARC 198, not here."
            ),
        },
    }


def _clean_yield(claims: pd.DataFrame) -> float:
    clean = claims[~claims["denied"]]
    billed = int(clean["billed_cents"].sum())
    if billed == 0:
        return 0.0
    return int(clean["paid_cents"].sum()) / billed


def _paid_per_unit_cents(claims: pd.DataFrame) -> float:
    paid = claims[claims["paid_cents"] > 0]
    units = int(paid["units"].sum())
    if units == 0:
        return 0.0
    return int(paid["paid_cents"].sum()) / units


def _age_bucket(age_days: int) -> str:
    if age_days <= 30:
        return "0-30"
    if age_days <= 60:
        return "31-60"
    if age_days <= 90:
        return "61-90"
    return "91+"


def retired_carc_note() -> str:
    retired = CARC_CATALOG["15"]
    stop = retired.stop_date.isoformat() if retired.stop_date else "2018"
    return (
        f"CARC 15 ({retired.description}) was stopped by X12 on {stop}. "
        "The sample workbook still groups authorization denials under CO-15. "
        "This book uses 197 and 198 and keeps the same combined count of 206."
    )
