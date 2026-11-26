"""Four-week action plan read off this book.

The counts are facts in the synthetic data. The dollars in the recovery model
stay in the model. A week card names the queue; it does not promise the collection.
"""

from __future__ import annotations

from up4u_audit.formatting import hours_from_units, money, percent
from up4u_audit.generator import AuditBook
from up4u_audit.roi import RoiAssumptions
from up4u_audit.targets import WEEKDAYS


def weekly_actions(book: AuditBook, assumptions: RoiAssumptions | None = None) -> list[dict]:
    assumptions = assumptions or RoiAssumptions()
    claims = book.claims
    denied = claims[claims["denied"]]
    unworked = denied[~denied["worked"]]
    inside = unworked[unworked["age_days"] <= assumptions.appeal_window_days]
    appointments = book.appointments

    def queue(code: str) -> tuple[int, int]:
        part = inside[inside["carc"].astype(str) == code]
        return len(part), int(part["billed_cents"].sum())

    carc_4_n, carc_4_billed = queue("4")
    carc_197_n, carc_197_billed = queue("197")
    carc_198_n, _carc_198_billed = queue("198")
    carc_27_n, carc_27_billed = queue("27")
    carc_29 = unworked[unworked["carc"].astype(str) == "29"]
    carc_29_n = len(carc_29)
    carc_29_billed = int(carc_29["billed_cents"].sum())

    payer_rows = []
    for payer, part in claims.groupby("payer"):
        payer_rows.append((int(part["denied"].sum()) / len(part), payer, len(part)))
    payer_rows.sort(reverse=True)
    worst_rate, worst_payer, worst_n = payer_rows[0]

    weekday_lines = []
    for weekday in WEEKDAYS:
        part = appointments[appointments["weekday"] == weekday]
        weekday_lines.append(
            (
                weekday,
                int((part["status"] == "no_show").sum()) / len(part),
                int((part["status"] == "late_cancel").sum()) / len(part),
            )
        )
    ranked = sorted(weekday_lines, key=lambda item: item[1], reverse=True)
    top_two = ranked[:2]
    midweek = [row for row in weekday_lines if row[0] in {"Tuesday", "Wednesday", "Thursday"}]

    open_unbooked_units = int(
        book.authorizations.loc[book.authorizations["status"] == "open", "unbooked_units"].sum()
    )
    open_unused_units = int(
        (
            book.authorizations.loc[book.authorizations["status"] == "open", "authorized_units"]
            - book.authorizations.loc[book.authorizations["status"] == "open", "used_units"]
        )
        .clip(lower=0)
        .sum()
    )

    window = assumptions.appeal_window_days
    return [
        {
            "week": 1,
            "title": "Resubmit the modifier denials still inside the window",
            "intent": (
                "CARC 4 is a claim defect: the procedure and the modifier disagree. "
                "Correct the claim and resubmit it. Do not start the week with timely filing."
            ),
            "lines": [
                (
                    f"Unworked CO-4 denials with a remittance age of {window} days or less: "
                    f"{carc_4_n} claims, {money(carc_4_billed)} billed."
                ),
                (
                    "Work those before older denials. A corrected modifier is a resubmission, "
                    "not a medical-necessity appeal."
                ),
                (
                    f"Set aside unworked CO-29 (timely filing): {carc_29_n} claims, "
                    f"{money(carc_29_billed)} billed. The model keeps that yield very low "
                    "because a missed deadline is rarely reversed."
                ),
            ],
        },
        {
            "week": 2,
            "title": "Separate missing authorizations from authorizations that ran out",
            "intent": (
                "CO-197 and CO-198 are different problems. One may still have a retro-authorization "
                "path. The other is already past the cap."
            ),
            "lines": [
                (
                    f"Unworked CO-197 inside {window} days: {carc_197_n} claims, "
                    f"{money(carc_197_billed)} billed. Confirm the authorization is actually absent "
                    "before writing an appeal."
                ),
                (
                    f"Unworked CO-198 inside {window} days: {carc_198_n} claims. "
                    "Those units are already over the authorization. The operating fix is to stop "
                    "scheduling past the cap, not to expect the extra units to pay."
                ),
                (
                    f"Still-open authorizations hold {hours_from_units(open_unused_units):.0f} unused hours, "
                    f"of which {hours_from_units(open_unbooked_units):.0f} were never scheduled. "
                    "Only the never-scheduled hours are in the model's fill assumption. "
                    "Missed visits are already in the attendance figures."
                ),
            ],
        },
        {
            "week": 3,
            "title": "Check eligibility before the visit for the weakest payer",
            "intent": (
                "CARC 27 means the payer says coverage had ended. Some of those will be real. "
                "The ones that are wrong are caught at the front desk, not in an appeal months later."
            ),
            "lines": [
                (
                    f"Unworked CO-27 inside {window} days: {carc_27_n} claims, "
                    f"{money(carc_27_billed)} billed."
                ),
                (
                    f"Highest denial rate in this book: {worst_payer} at "
                    f"{percent(worst_rate, 1)} on {worst_n} claims. "
                    "Run eligibility for that payer before the visit is kept."
                ),
                "A terminated plan does not become revenue because someone worked the denial.",
            ],
        },
        {
            "week": 4,
            "title": "Confirm the weekdays that already miss more often",
            "intent": (
                "In this book the no-show rate is not flat across the week. "
                "The change to test is operational and small."
            ),
            "lines": [
                (
                    f"Highest no-show weekdays: {top_two[0][0]} at {percent(top_two[0][1], 1)} "
                    f"(late cancel {percent(top_two[0][2], 1)}) and {top_two[1][0]} at "
                    f"{percent(top_two[1][1], 1)} (late cancel {percent(top_two[1][2], 1)})."
                ),
                (
                    "Tuesday through Thursday no-show rates in this book: "
                    + ", ".join(f"{name} {percent(rate, 1)}" for name, rate, _late in midweek)
                    + "."
                ),
                (
                    "Confirm those high days on the prior business day, and keep a short list of "
                    "families who can take a freed slot."
                ),
                (
                    f"The model assumes a {percent(assumptions.no_show_relative_reduction, 1)} relative "
                    f"drop in no-show units and {percent(assumptions.late_cancel_relative_reduction, 1)} "
                    "in late-cancel units over the next year. Those are assumptions, not a result from this clinic."
                ),
            ],
        },
    ]
