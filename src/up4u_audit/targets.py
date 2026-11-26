"""Shape of the sample workbook, plus the synthetic pieces the workbook did not include.

Dollar amounts are integer cents so the published totals can be matched exactly.
The workbook's Medicaid row is named Medi-Cal here: the demo clinic is a
California pediatric therapy practice. Claim counts, dollars, and denial counts
for that row are unchanged.

CARC 15 was stopped by X12 on 2018-05-01. The workbook's 206 CO-15 denials are
reallocated to current codes 197 and 198. The combined count is the same.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


def cents(amount: str) -> int:
    """Parse a '1234.56' dollar string into integer cents."""
    negative = amount.startswith("-")
    text = amount[1:] if negative else amount
    whole, frac = text.split(".")
    if len(frac) != 2 or not whole.isdigit() or not frac.isdigit():
        raise ValueError(f"expected dollars with two decimals, got {amount!r}")
    value = int(whole) * 100 + int(frac)
    return -value if negative else value


SNAPSHOT = date(2026, 7, 31)
PERIODS = (
    (date(2025, 8, 1), date(2026, 1, 31)),
    (date(2026, 2, 1), date(2026, 7, 31)),
)

# Kept visits equal claims. The schedule is larger than the workbook's 2,600
# appointment rows so a kept visit can be one claim and the no-show rate can
# stay 12.7%. 520 / 4094 = 12.7015% (12.7%). 174 / 4094 = 4.250% (4.3%).
SCHEDULED_APPOINTMENTS = 4094
NO_SHOWS = 520
LATE_CANCELS = 174
KEPT_VISITS = SCHEDULED_APPOINTMENTS - NO_SHOWS - LATE_CANCELS  # 3400

# Late cancels are not in the workbook. Weights tilt toward Monday and Friday,
# the weekdays the workbook already shows as high no-show days. This is a
# generator setting, not a measured rate.
LATE_CANCEL_DAY_WEIGHTS = {
    "Monday": 1.6,
    "Tuesday": 0.8,
    "Wednesday": 0.8,
    "Thursday": 0.9,
    "Friday": 1.6,
    "Saturday": 1.0,
    "Sunday": 0.9,
}

# Share of denied claims left unworked, by age of the remittance. Generator
# setting so the book has a visible aged queue. Not a published benchmark.
UNWORKED_SHARE_BY_BUCKET = {
    "0-30": 0.35,
    "31-60": 0.45,
    "61-90": 0.55,
    "91+": 0.62,
}

# Extra authorized units that were never put on the schedule, in 15-minute
# blocks (4 = 1 hour). Used only on authorizations that were not exceeded.
UNBOOKED_UNIT_CHOICES = (4, 8, 16)
UNBOOKED_UNIT_WEIGHTS = (50, 35, 15)

BILLED_MIN_CENTS = 65_00
BILLED_MAX_CENTS = 240_00
# Paid amount on a non-denied claim stays inside this band of billed charges.
PAID_LOW_RATIO = 0.50
PAID_HIGH_RATIO = 0.85
# Sample non-denied claims paid about 96.9% of the allowed amount.
PAID_TO_ALLOWED = 0.969

WEEKDAYS = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)


@dataclass(frozen=True)
class DayPattern:
    weekday: str
    appointments: int
    no_shows: int


# Appointment and no-show counts from the workbook's "No-Show Analysis" sheet.
SOURCE_DAYS = (
    DayPattern("Monday", 376, 69),
    DayPattern("Tuesday", 386, 35),
    DayPattern("Wednesday", 355, 34),
    DayPattern("Thursday", 359, 38),
    DayPattern("Friday", 384, 68),
    DayPattern("Saturday", 368, 45),
    DayPattern("Sunday", 372, 42),
)


@dataclass(frozen=True)
class Clinician:
    name: str
    credential: str
    service_line: str
    role: str
    appointments: int
    no_shows: int


# Names are the synthetic labels in the sample workbook: initial, surname, credential.
CLINICIANS = (
    Clinician("R. Kim, OTR/L", "OTR/L", "OT", "ot", 428, 64),
    Clinician("J. Alvarez, MA-BCBA", "MA-BCBA", "ABA", "bcba", 422, 63),
    Clinician("S. Patel, SLP", "SLP", "SLP", "slp", 437, 53),
    Clinician("L. Brooks, RBT", "RBT", "ABA", "rbt", 409, 49),
    Clinician("M. Nguyen, MA-BCBA", "MA-BCBA", "ABA", "bcba", 438, 52),
    Clinician("D. Ortiz, PT", "PT", "PT", "pt", 466, 50),
)

# Share of a BCBA's visits by CPT. Generator setting so BCBAs bill assessment,
# supervision, and parent guidance rather than every code in the clinic.
BCBA_CPT_WEIGHTS = {"97151": 15, "97153": 20, "97155": 45, "97156": 20}

CPT_CATALOG = {
    "97151": {
        "service_line": "ABA",
        "description": "Behavior identification assessment",
        "units": 8,
    },
    "97153": {
        "service_line": "ABA",
        "description": "Adaptive behavior treatment by protocol",
        "units": 8,
    },
    "97155": {
        "service_line": "ABA",
        "description": "Adaptive behavior treatment with protocol modification",
        "units": 4,
    },
    "97156": {
        "service_line": "ABA",
        "description": "Family adaptive behavior treatment guidance",
        "units": 4,
    },
    "92507": {
        "service_line": "SLP",
        "description": "Speech, language, or hearing treatment",
        "units": 4,
    },
    "97110": {
        "service_line": "PT",
        "description": "Therapeutic exercise",
        "units": 4,
    },
    "97535": {
        "service_line": "OT",
        "description": "Self-care/home management training",
        "units": 4,
    },
}

ROLE_CPT = {
    "rbt": "97153",
    "slp": "92507",
    "ot": "97535",
    "pt": "97110",
}


@dataclass(frozen=True)
class Payer:
    id: str
    name: str
    category: str
    claims: int
    billed_cents: int
    paid_cents: int
    denials: int


PAYERS = (
    Payer("medi_cal", "Medi-Cal (State Plan)", "medi_cal", 1032, cents("157653.77"), cents("80728.39"), 252),
    Payer("anthem", "Anthem HMO", "commercial", 504, cents("79257.74"), cents("41293.42"), 120),
    Payer("aetna_bh", "Aetna Better Health", "medi_cal_managed", 505, cents("75452.17"), cents("40058.65"), 107),
    Payer("uhc", "United Healthcare", "commercial", 487, cents("75130.83"), cents("40549.04"), 96),
    Payer("blueshield", "Blue Shield PPO", "commercial", 610, cents("92682.28"), cents("52452.66"), 101),
    Payer("self_pay", "Self-Pay", "self_pay", 262, cents("40280.24"), cents("26149.00"), 9),
)

CATEGORY_LABELS = {
    "medi_cal": "Medi-Cal",
    "medi_cal_managed": "Managed Medi-Cal",
    "commercial": "Commercial",
    "self_pay": "Self-pay",
}

# Workbook CO-15 count of 206, split across the two current authorization codes.
DENIALS_BY_PAYER: dict[str, dict[str, int]] = {
    "medi_cal": {"197": 55, "198": 35, "27": 72, "50": 40, "4": 32, "29": 18},
    "anthem": {"197": 20, "198": 16, "27": 36, "50": 18, "4": 18, "29": 12},
    "aetna_bh": {"197": 18, "198": 14, "27": 34, "50": 16, "4": 15, "29": 10},
    "uhc": {"197": 14, "198": 10, "27": 30, "50": 14, "4": 16, "29": 12},
    "blueshield": {"197": 11, "198": 11, "27": 28, "50": 19, "4": 17, "29": 15},
    "self_pay": {"197": 0, "198": 2, "27": 3, "50": 2, "4": 2, "29": 0},
}

WORKBOOK_CO15_DENIALS = 206
ACTIVE_CARCS = ("197", "198", "27", "50", "4", "29")


@dataclass(frozen=True)
class MonthTarget:
    month: str
    billed_cents: int
    paid_cents: int


MONTHS = (
    MonthTarget("2025-08", cents("46872.22"), cents("25766.01")),
    MonthTarget("2025-09", cents("43219.76"), cents("23728.42")),
    MonthTarget("2025-10", cents("39711.87"), cents("19939.71")),
    MonthTarget("2025-11", cents("40753.36"), cents("22070.98")),
    MonthTarget("2025-12", cents("42919.27"), cents("23155.75")),
    MonthTarget("2026-01", cents("45032.38"), cents("24813.45")),
    MonthTarget("2026-02", cents("44807.69"), cents("24333.31")),
    MonthTarget("2026-03", cents("44504.73"), cents("23953.41")),
    MonthTarget("2026-04", cents("43422.10"), cents("23373.69")),
    MonthTarget("2026-05", cents("43536.95"), cents("22866.61")),
    MonthTarget("2026-06", cents("44988.59"), cents("24395.95")),
    MonthTarget("2026-07", cents("40688.11"), cents("22833.87")),
)

DEFAULT_SEED = 7
MINUTES_PER_UNIT = 15
PATIENTS_PER_CLAIMS = 40


def validate_targets() -> None:
    if KEPT_VISITS != 3400:
        raise RuntimeError("kept visits must equal the workbook claim count of 3,400")
    if sum(d.appointments for d in SOURCE_DAYS) != 2600:
        raise RuntimeError("workbook weekday appointments must sum to 2,600")
    if sum(d.no_shows for d in SOURCE_DAYS) != 331:
        raise RuntimeError("workbook weekday no-shows must sum to 331")
    if sum(c.appointments for c in CLINICIANS) != 2600:
        raise RuntimeError("workbook clinician appointments must sum to 2,600")
    if sum(c.no_shows for c in CLINICIANS) != 331:
        raise RuntimeError("workbook clinician no-shows must sum to 331")

    billed = sum(p.billed_cents for p in PAYERS)
    paid = sum(p.paid_cents for p in PAYERS)
    claims = sum(p.claims for p in PAYERS)
    denials = sum(p.denials for p in PAYERS)
    if claims != KEPT_VISITS or denials != 685:
        raise RuntimeError("payer claim or denial totals drifted")
    if billed != sum(m.billed_cents for m in MONTHS):
        raise RuntimeError("payer and month billed totals differ")
    if paid != sum(m.paid_cents for m in MONTHS):
        raise RuntimeError("payer and month paid totals differ")
    if billed != cents("520457.03") or paid != cents("281231.16"):
        raise RuntimeError("published billed or paid total drifted")

    for payer in PAYERS:
        row = DENIALS_BY_PAYER[payer.id]
        if sum(row.values()) != payer.denials:
            raise RuntimeError(f"denial codes for {payer.id} do not match the payer total")
        if set(row) != set(ACTIVE_CARCS):
            raise RuntimeError(f"denial codes for {payer.id} are incomplete")
    for code in ACTIVE_CARCS:
        # Touch every column so a typo fails at import.
        sum(DENIALS_BY_PAYER[p.id][code] for p in PAYERS)
    auth_denials = sum(DENIALS_BY_PAYER[p.id]["197"] + DENIALS_BY_PAYER[p.id]["198"] for p in PAYERS)
    if auth_denials != WORKBOOK_CO15_DENIALS:
        raise RuntimeError("197 + 198 must equal the workbook's retired CO-15 count")


validate_targets()
