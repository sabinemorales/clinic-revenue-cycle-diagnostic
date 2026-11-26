"""A small recovery model with the assumptions written on the face of it.

One-time dollars are a rework of denials nobody has touched, plus a fraction
of still-open hours that were never scheduled. Next-year dollars are the
capacity from a lower no-show and late-cancel rate if the next year looks
like this one. Those two piles are not added, and neither is a payback period.

Every rate below is an assumption. None of them is a published success rate.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import pandas as pd

from up4u_audit.analysis import _clean_yield, _paid_per_unit_cents
from up4u_audit.carc import DISPLAY_ORDER, get_carc
from up4u_audit.formatting import hours_from_units, money, percent
from up4u_audit.generator import AuditBook

CAVEAT = (
    "These are planning estimates under the assumptions in this model, not a forecast "
    "and not a promise of recovery. One-time dollars and next-year capacity dollars "
    "are different and are not combined into a payback period."
)


@dataclass(frozen=True)
class RoiAssumptions:
    """Adjustable assumptions. Defaults are deliberately modest."""

    audit_fee_cents: int = 120_000
    appeal_window_days: int = 90
    # Applied when the remittance is older than the appeal window.
    outside_window_multiplier: float = 0.25
    # Share of billed charges assumed collectible if an unworked denial is reworked,
    # before multiplying by the clinic's own clean-claim yield.
    rework_yield_4: float = 0.55
    rework_yield_197: float = 0.25
    rework_yield_198: float = 0.15
    rework_yield_27: float = 0.20
    rework_yield_50: float = 0.10
    rework_yield_29: float = 0.02
    # Relative reduction in missed units over the next year, if the clinic
    # changes confirmation and backfill. Not an observed result.
    no_show_relative_reduction: float = 0.20
    late_cancel_relative_reduction: float = 0.10
    # Share of still-open, never-scheduled authorized units assumed fillable.
    # Missed-visit units are left out of this rate so they are not counted twice.
    open_unbooked_fill_rate: float = 0.30
    # Low case is this share of the illustrative dollars. It does not invent
    # a second, harsher set of rates, and there is no case above the rates
    # as entered.
    low_factor: float = 0.50
    horizon_months: int = 12

    def __post_init__(self) -> None:
        rates = {
            "outside_window_multiplier": self.outside_window_multiplier,
            "rework_yield_4": self.rework_yield_4,
            "rework_yield_197": self.rework_yield_197,
            "rework_yield_198": self.rework_yield_198,
            "rework_yield_27": self.rework_yield_27,
            "rework_yield_50": self.rework_yield_50,
            "rework_yield_29": self.rework_yield_29,
            "no_show_relative_reduction": self.no_show_relative_reduction,
            "late_cancel_relative_reduction": self.late_cancel_relative_reduction,
            "open_unbooked_fill_rate": self.open_unbooked_fill_rate,
            "low_factor": self.low_factor,
        }
        for name, value in rates.items():
            if not 0 <= float(value) <= 1:
                raise ValueError(f"{name} must be between 0 and 1")
        if self.appeal_window_days < 0:
            raise ValueError("appeal_window_days must be nonnegative")
        if self.audit_fee_cents < 0:
            raise ValueError("audit_fee_cents must be nonnegative")
        if self.horizon_months <= 0:
            raise ValueError("horizon_months must be positive")

    def yield_for(self, code: str) -> float:
        return {
            "4": self.rework_yield_4,
            "197": self.rework_yield_197,
            "198": self.rework_yield_198,
            "27": self.rework_yield_27,
            "50": self.rework_yield_50,
            "29": self.rework_yield_29,
        }[str(code)]


def estimate_roi(book: AuditBook, assumptions: RoiAssumptions | None = None) -> dict:
    assumptions = assumptions or RoiAssumptions()
    base = _estimate(book, assumptions)
    low = _scale_estimate(base, assumptions.low_factor)
    fee = assumptions.audit_fee_cents
    return {
        "clean_yield": base["clean_yield"],
        "paid_per_unit_cents": base["paid_per_unit_cents"],
        "audit_fee_cents": fee,
        "caveat": CAVEAT,
        "one_time": {
            "denial_rework_cents": base["denial_rework_cents"],
            "open_unbooked_fill_cents": base["open_unbooked_fill_cents"],
            "total_cents": base["one_time_cents"],
            "low_cents": low["one_time_cents"],
            "net_of_fee_cents": base["one_time_cents"] - fee,
            "low_net_of_fee_cents": low["one_time_cents"] - fee,
        },
        "annualized": {
            "no_show_cents": base["no_show_cents"],
            "late_cancel_cents": base["late_cancel_cents"],
            "total_cents": base["annualized_cents"],
            "low_cents": low["annualized_cents"],
            "horizon_months": assumptions.horizon_months,
        },
        "by_carc": _merge_carc(base["by_carc"], low["by_carc"]),
        "assumptions": assumption_rows(assumptions),
    }


def assumption_rows(assumptions: RoiAssumptions | None = None) -> list[dict]:
    assumptions = assumptions or RoiAssumptions()
    return [
        {
            "assumption": "Audit fee",
            "value": money(assumptions.audit_fee_cents),
            "role": "Fixed fee for the 10-business-day No-Show Recovery Audit. Not a percentage of recovery.",
        },
        {
            "assumption": "Appeal window",
            "value": f"{assumptions.appeal_window_days} days from remit",
            "role": "Working cutoff for a full rework yield. Not a legal filing deadline; payer rules differ.",
        },
        {
            "assumption": "Outside-window multiplier",
            "value": percent(assumptions.outside_window_multiplier, 1),
            "role": "Share of the code's rework yield still applied once the remittance is older than the window.",
        },
        {
            "assumption": "CARC 4 rework yield",
            "value": percent(assumptions.rework_yield_4, 1),
            "role": "Assumed share of billed charges collected if an unworked modifier denial is corrected and resubmitted, before the clean-claim yield.",
        },
        {
            "assumption": "CARC 197 rework yield",
            "value": percent(assumptions.rework_yield_197, 1),
            "role": "Assumed share if a missing authorization can still be obtained or documented. Often it cannot.",
        },
        {
            "assumption": "CARC 198 rework yield",
            "value": percent(assumptions.rework_yield_198, 1),
            "role": "Assumed share if units billed past the authorization are paid on appeal. Usually this is a prospective fix, so the yield stays low.",
        },
        {
            "assumption": "CARC 27 rework yield",
            "value": percent(assumptions.rework_yield_27, 1),
            "role": "Assumed share if eligibility had not actually ended. A real termination does not become revenue.",
        },
        {
            "assumption": "CARC 50 rework yield",
            "value": percent(assumptions.rework_yield_50, 1),
            "role": "Assumed share of medical-necessity denials won on appeal. Appeals are slow and often lost.",
        },
        {
            "assumption": "CARC 29 rework yield",
            "value": percent(assumptions.rework_yield_29, 1),
            "role": "Assumed share after a missed filing deadline. Treated as almost never recovered.",
        },
        {
            "assumption": "Clean-claim yield",
            "value": "Measured from this book",
            "role": "Paid divided by billed on claims that were not denied. Rework estimates are multiplied by it, because the clinic does not collect its full charge.",
        },
        {
            "assumption": "No-show reduction",
            "value": percent(assumptions.no_show_relative_reduction, 1) + " relative",
            "role": "Assumed drop in no-show units over the next year if confirmation and backfill change. Not a result observed in this book.",
        },
        {
            "assumption": "Late-cancel reduction",
            "value": percent(assumptions.late_cancel_relative_reduction, 1) + " relative",
            "role": "Assumed drop in late-cancel units over the next year. Set lower than the no-show figure because illness and other real conflicts remain.",
        },
        {
            "assumption": "Open unbooked fill rate",
            "value": percent(assumptions.open_unbooked_fill_rate, 1),
            "role": "Assumed share of still-open authorized units that were never scheduled and could still be booked. Missed visits are not in this pile.",
        },
        {
            "assumption": "Low case",
            "value": percent(assumptions.low_factor, 1) + " of the illustrative dollars",
            "role": "The low estimate is this share of the dollars produced by the rates as entered. The fee is not scaled. There is no estimate above those rates.",
        },
    ]


def _estimate(book: AuditBook, assumptions: RoiAssumptions) -> dict:
    claims = book.claims
    clean_yield = _clean_yield(claims)
    paid_per_unit = _paid_per_unit_cents(claims)
    denied = claims[claims["denied"] & ~claims["worked"]]
    by_carc = []
    rework = 0.0
    for code in DISPLAY_ORDER:
        part = denied[denied["carc"].astype(str) == code]
        yield_rate = assumptions.yield_for(code)
        amount = 0.0
        inside = 0
        for row in part.itertuples(index=False):
            multiplier = (
                1.0
                if int(row.age_days) <= assumptions.appeal_window_days
                else assumptions.outside_window_multiplier
            )
            amount += int(row.billed_cents) * yield_rate * multiplier * clean_yield
            if int(row.age_days) <= assumptions.appeal_window_days:
                inside += 1
        rework += amount
        by_carc.append(
            {
                "carc": code,
                "code": get_carc(code).display_code,
                "short_label": get_carc(code).short_label,
                "unworked_claims": len(part),
                "inside_window_claims": inside,
                "rework_cents": int(round(amount)),
            }
        )

    open_unbooked = int(
        book.authorizations.loc[book.authorizations["status"] == "open", "unbooked_units"].sum()
    )
    fill = open_unbooked * assumptions.open_unbooked_fill_rate * paid_per_unit
    no_show_units = int(book.appointments.loc[book.appointments["status"] == "no_show", "units"].sum())
    late_units = int(book.appointments.loc[book.appointments["status"] == "late_cancel", "units"].sum())
    no_show = no_show_units * assumptions.no_show_relative_reduction * paid_per_unit
    late = late_units * assumptions.late_cancel_relative_reduction * paid_per_unit
    return {
        "clean_yield": clean_yield,
        "paid_per_unit_cents": paid_per_unit,
        "denial_rework_cents": int(round(rework)),
        "open_unbooked_fill_cents": int(round(fill)),
        "one_time_cents": int(round(rework)) + int(round(fill)),
        "no_show_cents": int(round(no_show)),
        "late_cancel_cents": int(round(late)),
        "annualized_cents": int(round(no_show)) + int(round(late)),
        "by_carc": by_carc,
    }


def _scale_estimate(base: dict, factor: float) -> dict:
    """Low case: the same arithmetic, scaled. Rounding is redone per piece."""
    by_carc = []
    rework = 0
    for row in base["by_carc"]:
        amount = int(round(row["rework_cents"] * factor))
        rework += amount
        by_carc.append({**row, "rework_cents": amount})
    fill = int(round(base["open_unbooked_fill_cents"] * factor))
    no_show = int(round(base["no_show_cents"] * factor))
    late = int(round(base["late_cancel_cents"] * factor))
    return {
        "clean_yield": base["clean_yield"],
        "paid_per_unit_cents": base["paid_per_unit_cents"],
        "denial_rework_cents": rework,
        "open_unbooked_fill_cents": fill,
        "one_time_cents": rework + fill,
        "no_show_cents": no_show,
        "late_cancel_cents": late,
        "annualized_cents": no_show + late,
        "by_carc": by_carc,
    }


def _merge_carc(base_rows: list[dict], low_rows: list[dict]) -> list[dict]:
    low_by_code = {row["carc"]: row["rework_cents"] for row in low_rows}
    merged = []
    for row in base_rows:
        merged.append({**row, "low_rework_cents": low_by_code[row["carc"]]})
    return merged


def zeroed_assumptions() -> RoiAssumptions:
    """Every rate at zero, for the boundary test. Fee and window stay."""
    return replace(
        RoiAssumptions(),
        outside_window_multiplier=0.0,
        rework_yield_4=0.0,
        rework_yield_197=0.0,
        rework_yield_198=0.0,
        rework_yield_27=0.0,
        rework_yield_50=0.0,
        rework_yield_29=0.0,
        no_show_relative_reduction=0.0,
        late_cancel_relative_reduction=0.0,
        open_unbooked_fill_rate=0.0,
    )


def carc_rework_frame(estimate: dict) -> pd.DataFrame:
    return pd.DataFrame(estimate["by_carc"])


def hours_open_unbooked(book: AuditBook) -> float:
    units = int(book.authorizations.loc[book.authorizations["status"] == "open", "unbooked_units"].sum())
    return hours_from_units(units)
