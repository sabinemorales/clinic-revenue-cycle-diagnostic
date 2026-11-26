"""Current X12 Claim Adjustment Reason Codes used by the audit.

Descriptions are the X12 wording, without the separate "Usage" note.
Source: X12 Claim Adjustment Reason Codes, https://x12.org/codes/claim-adjustment-reason-codes
Code 15 stop date is 2018-05-01 on that list. Code 4's description is the
current sentence, which no longer mentions a missing modifier.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Carc:
    code: str
    description: str
    short_label: str
    retired: bool = False
    stop_date: date | None = None
    usage: str = ""

    @property
    def display_code(self) -> str:
        return f"CO-{self.code}"


_USAGE = (
    "Refer to the 835 Healthcare Policy Identification Segment "
    "(loop 2110 Service Payment Information REF), if present."
)

CARC_CATALOG: dict[str, Carc] = {
    "4": Carc(
        code="4",
        description="The procedure code is inconsistent with the modifier used.",
        short_label="Procedure/modifier inconsistent",
        usage=_USAGE,
    ),
    "15": Carc(
        code="15",
        description=(
            "The authorization number is missing, invalid, or does not apply "
            "to the billed services or provider."
        ),
        short_label="Authorization number missing/invalid",
        retired=True,
        stop_date=date(2018, 5, 1),
    ),
    "27": Carc(
        code="27",
        description="Expenses incurred after coverage terminated.",
        short_label="Coverage terminated",
    ),
    "29": Carc(
        code="29",
        description="The time limit for filing has expired.",
        short_label="Timely filing expired",
    ),
    "50": Carc(
        code="50",
        description=(
            "These are non-covered services because this is not deemed a "
            "'medical necessity' by the payer."
        ),
        short_label="Medical necessity",
        usage=_USAGE,
    ),
    "197": Carc(
        code="197",
        description="Precertification/authorization/notification/pre-treatment absent.",
        short_label="Authorization absent",
    ),
    "198": Carc(
        code="198",
        description="Precertification/notification/authorization/pre-treatment exceeded.",
        short_label="Authorization exceeded",
    ),
}

# Order used in tables: authorization, eligibility, necessity, coding, filing.
DISPLAY_ORDER = ("197", "198", "27", "50", "4", "29")


def get_carc(code: str) -> Carc:
    try:
        return CARC_CATALOG[str(code)]
    except KeyError as exc:
        raise KeyError(f"unknown CARC {code}") from exc
