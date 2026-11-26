"""Seeded synthetic book for one pediatric therapy clinic.

The claim totals, payer mix, monthly dollars, and denial counts match the
sample workbook. Authorization denials use CARC 197 and 198 instead of the
retired CARC 15. Appointments, late cancels, authorizations, and the
worked/unworked flag are built so those leaks can be shown; the workbook
did not contain them.

Patients are ids only. There are no names, birth dates, addresses, or
member numbers.

Default seed is 7. The same seed returns the same frames.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta

import numpy as np
import pandas as pd

from up4u_audit.fitting import integer_matrix, largest_remainder, shift_to_caps, split_exact
from up4u_audit.targets import (
    ACTIVE_CARCS,
    BCBA_CPT_WEIGHTS,
    BILLED_MAX_CENTS,
    BILLED_MIN_CENTS,
    CATEGORY_LABELS,
    CLINICIANS,
    CPT_CATALOG,
    DEFAULT_SEED,
    DENIALS_BY_PAYER,
    KEPT_VISITS,
    LATE_CANCEL_DAY_WEIGHTS,
    LATE_CANCELS,
    MONTHS,
    NO_SHOWS,
    PAID_HIGH_RATIO,
    PAID_LOW_RATIO,
    PAID_TO_ALLOWED,
    PATIENTS_PER_CLAIMS,
    PAYERS,
    PERIODS,
    ROLE_CPT,
    SCHEDULED_APPOINTMENTS,
    SNAPSHOT,
    SOURCE_DAYS,
    UNBOOKED_UNIT_CHOICES,
    UNBOOKED_UNIT_WEIGHTS,
    UNWORKED_SHARE_BY_BUCKET,
    WEEKDAYS,
)

PAYER_BY_ID = {payer.id: payer for payer in PAYERS}
CLINICIAN_BY_NAME = {clinician.name: clinician for clinician in CLINICIANS}


@dataclass
class AuditBook:
    appointments: pd.DataFrame
    claims: pd.DataFrame
    authorizations: pd.DataFrame
    patients: pd.DataFrame
    seed: int
    snapshot: date


def generate(seed: int = DEFAULT_SEED) -> AuditBook:
    rng = np.random.default_rng(seed)
    appointments = _appointments(rng)
    _assign_cpts(appointments)
    _assign_dates(appointments)
    _assign_payers(appointments, rng)
    _assign_patients(appointments)
    claims = _claims_from_kept(appointments)
    _assign_denials(claims, rng)
    authorizations = _authorizations(appointments, claims, rng)
    _assign_dollars(claims, rng)
    _assign_ids(appointments, claims, authorizations)
    _finalize_followup(claims, rng)

    return AuditBook(
        appointments=_frame(appointments, _APPOINTMENT_COLUMNS),
        claims=_frame(claims, _CLAIM_COLUMNS),
        authorizations=_frame(authorizations, _AUTH_COLUMNS),
        patients=_patient_frame(appointments),
        seed=seed,
        snapshot=SNAPSHOT,
    )


_APPOINTMENT_COLUMNS = [
    "appointment_id",
    "service_date",
    "month",
    "weekday",
    "patient_id",
    "clinician",
    "credential",
    "service_line",
    "cpt",
    "units",
    "payer",
    "payer_category",
    "status",
]

_CLAIM_COLUMNS = [
    "claim_id",
    "appointment_id",
    "patient_id",
    "service_date",
    "month",
    "remit_date",
    "age_days",
    "clinician",
    "service_line",
    "cpt",
    "units",
    "payer",
    "payer_category",
    "billed_cents",
    "allowed_cents",
    "paid_cents",
    "denied",
    "carc",
    "denial_group",
    "auth_id",
    "worked",
]

_AUTH_COLUMNS = [
    "auth_id",
    "patient_id",
    "payer",
    "payer_category",
    "service_line",
    "clinician",
    "period_start",
    "period_end",
    "authorized_units",
    "used_units",
    "missed_units",
    "unbooked_units",
    "exceeded_units",
    "status",
]


def _frame(rows: list[dict], columns: list[str]) -> pd.DataFrame:
    frame = pd.DataFrame(rows, columns=columns)
    return frame.sort_values(columns[0], kind="mergesort").reset_index(drop=True)


def _appointments(rng: np.random.Generator) -> list[dict]:
    day_counts = largest_remainder(
        [day.appointments for day in SOURCE_DAYS], SCHEDULED_APPOINTMENTS
    )
    clinician_counts = largest_remainder(
        [clinician.appointments for clinician in CLINICIANS], SCHEDULED_APPOINTMENTS
    )
    no_show_days = _scaled_events(
        day_counts,
        [day.appointments for day in SOURCE_DAYS],
        [day.no_shows for day in SOURCE_DAYS],
        NO_SHOWS,
    )
    no_show_clinicians = _scaled_events(
        clinician_counts,
        [clinician.appointments for clinician in CLINICIANS],
        [clinician.no_shows for clinician in CLINICIANS],
        NO_SHOWS,
    )

    no_shows = integer_matrix(no_show_days, no_show_clinicians)
    rest_rows = [day_counts[i] - int(no_shows[i].sum()) for i in range(len(day_counts))]
    rest_cols = [clinician_counts[j] - int(no_shows[:, j].sum()) for j in range(len(clinician_counts))]
    if any(value < 0 for value in rest_rows + rest_cols):
        raise RuntimeError("no-show margins exceed the schedule")
    rest = integer_matrix(rest_rows, rest_cols)

    late_days = largest_remainder(
        [LATE_CANCEL_DAY_WEIGHTS[day.weekday] * rest_rows[i] for i, day in enumerate(SOURCE_DAYS)],
        LATE_CANCELS,
    )
    late_days = shift_to_caps(late_days, rest_rows)
    late_clinicians = largest_remainder(rest_cols, LATE_CANCELS)
    late_clinicians = shift_to_caps(late_clinicians, rest_cols)
    late = integer_matrix(late_days, late_clinicians)
    if np.any(late > rest):
        late = _enforce_upper_bound(late, rest)

    rows: list[dict] = []
    for i, day in enumerate(SOURCE_DAYS):
        for j, clinician in enumerate(CLINICIANS):
            _append_status(rows, day.weekday, clinician, "no_show", int(no_shows[i, j]))
            _append_status(rows, day.weekday, clinician, "late_cancel", int(late[i, j]))
            kept = int(rest[i, j] - late[i, j])
            if kept < 0:
                raise RuntimeError("late cancels exceed non-no-show visits")
            _append_status(rows, day.weekday, clinician, "kept", kept)

    if sum(row["status"] == "kept" for row in rows) != KEPT_VISITS:
        raise RuntimeError("kept visits did not land on 3,400")

    order = rng.permutation(len(rows))
    shuffled = [rows[int(i)] for i in order]
    _assign_months(shuffled)
    return shuffled


def _scaled_events(
    new_population: list[int],
    source_population: list[int],
    source_events: list[int],
    new_events: int,
) -> list[int]:
    expected = [
        new_population[i] * source_events[i] / source_population[i]
        for i in range(len(new_population))
    ]
    scaled = largest_remainder(expected, new_events)
    return shift_to_caps(scaled, new_population)


def _append_status(rows: list[dict], weekday: str, clinician, status: str, count: int) -> None:
    for _ in range(count):
        rows.append(
            {
                "weekday": weekday,
                "clinician": clinician.name,
                "credential": clinician.credential,
                "service_line": clinician.service_line,
                "role": clinician.role,
                "status": status,
                "month": "",
                "service_date": None,
                "cpt": "",
                "units": 0,
                "payer": "",
                "payer_category": "",
                "patient_id": "",
                "appointment_id": "",
            }
        )


def _enforce_upper_bound(matrix: np.ndarray, caps: np.ndarray) -> np.ndarray:
    values = matrix.copy()
    guard = 0
    while np.any(values > caps):
        i, j = [int(x) for x in np.argwhere(values > caps)[0]]
        moved = False
        for k in range(values.shape[1]):
            if k == j or values[i, k] >= caps[i, k]:
                continue
            for t in range(values.shape[0]):
                if t == i:
                    continue
                if values[t, k] > 0 and values[t, j] < caps[t, j]:
                    values[i, j] -= 1
                    values[i, k] += 1
                    values[t, j] += 1
                    values[t, k] -= 1
                    moved = True
                    break
            if moved:
                break
        if not moved:
            raise RuntimeError("could not keep late cancels inside the schedule")
        guard += 1
        if guard > 10000:
            raise RuntimeError("late-cancel repair took too many steps")
    # Margins are preserved by the cycle, but check the total.
    if int(values.sum()) != int(matrix.sum()):
        raise RuntimeError("late-cancel repair changed the total")
    return values


def _assign_months(rows: list[dict]) -> None:
    month_names = [month.month for month in MONTHS]
    billed = [month.billed_cents for month in MONTHS]
    kept_by_month = largest_remainder(billed, KEPT_VISITS)
    other_count = len(rows) - KEPT_VISITS
    other_by_month = largest_remainder(billed, other_count)

    kept = [row for row in rows if row["status"] == "kept"]
    other = [row for row in rows if row["status"] != "kept"]
    _fill_months(kept, month_names, kept_by_month)
    _fill_months(other, month_names, other_by_month)


def _fill_months(rows: list[dict], months: list[str], counts: list[int]) -> None:
    if sum(counts) != len(rows):
        raise RuntimeError("month allocation does not match the rows")
    cursor = 0
    for month, count in zip(months, counts):
        for row in rows[cursor : cursor + count]:
            row["month"] = month
        cursor += count


def _calendar() -> dict[str, dict[str, list[date]]]:
    start = PERIODS[0][0]
    end = SNAPSHOT
    found: dict[str, dict[str, list[date]]] = defaultdict(lambda: defaultdict(list))
    day = start
    while day <= end:
        found[day.strftime("%Y-%m")][day.strftime("%A")].append(day)
        day += timedelta(days=1)
    return found


def _assign_dates(rows: list[dict]) -> None:
    calendar = _calendar()
    cursors: dict[tuple[str, str], int] = defaultdict(int)
    for row in rows:
        pool = calendar[row["month"]][row["weekday"]]
        if not pool:
            raise RuntimeError(f"no {row['weekday']} in {row['month']}")
        key = (row["month"], row["weekday"])
        row["service_date"] = pool[cursors[key] % len(pool)]
        cursors[key] += 1


def _assign_cpts(rows: list[dict]) -> None:
    by_clinician: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_clinician[row["clinician"]].append(row)
    for name, group in by_clinician.items():
        clinician = CLINICIAN_BY_NAME[name]
        if clinician.role == "bcba":
            weights = [BCBA_CPT_WEIGHTS[code] for code in BCBA_CPT_WEIGHTS]
            codes = list(BCBA_CPT_WEIGHTS)
            allocation = largest_remainder(weights, len(group))
            cursor = 0
            ordered = sorted(group, key=lambda item: (item["month"], item["weekday"], item["status"]))
            for code, count in zip(codes, allocation):
                for row in ordered[cursor : cursor + count]:
                    row["cpt"] = code
                    row["units"] = CPT_CATALOG[code]["units"]
                cursor += count
        else:
            code = ROLE_CPT[clinician.role]
            for row in group:
                row["cpt"] = code
                row["units"] = CPT_CATALOG[code]["units"]


def _assign_payers(rows: list[dict], rng: np.random.Generator) -> None:
    month_names = [month.month for month in MONTHS]
    kept_counts = [
        sum(row["status"] == "kept" and row["month"] == month for row in rows) for month in month_names
    ]
    payer_counts = [payer.claims for payer in PAYERS]
    payer_month = integer_matrix(payer_counts, kept_counts)

    for month_index, month in enumerate(month_names):
        kept = [row for row in rows if row["status"] == "kept" and row["month"] == month]
        labels: list[str] = []
        for payer_index, payer in enumerate(PAYERS):
            labels.extend([payer.id] * int(payer_month[payer_index, month_index]))
        if len(labels) != len(kept):
            raise RuntimeError(f"payer allocation missed {month}")
        order = rng.permutation(len(labels))
        for row, label_index in zip(kept, order):
            _set_payer(row, labels[int(label_index)])

    others = [row for row in rows if row["status"] != "kept"]
    other_labels = _repeat_to_length([payer.id for payer in PAYERS], payer_counts, len(others))
    order = rng.permutation(len(other_labels))
    for row, label_index in zip(others, order):
        _set_payer(row, other_labels[int(label_index)])


def _repeat_to_length(labels: list[str], weights: list[int], length: int) -> list[str]:
    counts = largest_remainder(weights, length)
    out: list[str] = []
    for label, count in zip(labels, counts):
        out.extend([label] * count)
    return out


def _set_payer(row: dict, payer_id: str) -> None:
    payer = PAYER_BY_ID[payer_id]
    row["payer"] = payer.name
    row["payer_category"] = CATEGORY_LABELS[payer.category]
    row["payer_id"] = payer.id


def _assign_patients(rows: list[dict]) -> None:
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        groups[(row["clinician"], row["payer_id"])].append(row)

    patient_index = 1
    for key in sorted(groups):
        group = groups[key]
        kept = sum(row["status"] == "kept" for row in group)
        panel = max(1, int(np.ceil(max(kept, 1) / PATIENTS_PER_CLAIMS)))
        ids = [f"SC-{patient_index + offset:03d}" for offset in range(panel)]
        patient_index += panel
        ordered = sorted(group, key=lambda item: (item["service_date"], item["status"], item["cpt"]))
        for offset, row in enumerate(ordered):
            row["patient_id"] = ids[offset % panel]


def _claims_from_kept(rows: list[dict]) -> list[dict]:
    claims = []
    for row in rows:
        if row["status"] != "kept":
            continue
        claims.append(
            {
                "appointment_id": "",
                "patient_id": row["patient_id"],
                "service_date": row["service_date"],
                "month": row["month"],
                "clinician": row["clinician"],
                "service_line": row["service_line"],
                "cpt": row["cpt"],
                "units": row["units"],
                "payer": row["payer"],
                "payer_category": row["payer_category"],
                "payer_id": row["payer_id"],
                "denied": False,
                "carc": None,
                "denial_group": None,
                "auth_id": None,
                "billed_cents": 0,
                "allowed_cents": 0,
                "paid_cents": 0,
                "remit_date": None,
                "age_days": 0,
                "worked": True,
                "claim_id": "",
                "_appointment": row,
            }
        )
    return claims


def _assign_denials(claims: list[dict], rng: np.random.Generator) -> None:
    by_payer: dict[str, list[dict]] = defaultdict(list)
    for claim in claims:
        by_payer[claim["payer_id"]].append(claim)

    for payer in PAYERS:
        group = by_payer[payer.id]
        by_month: dict[str, list[dict]] = defaultdict(list)
        for claim in group:
            by_month[claim["month"]].append(claim)
        month_sizes = [len(by_month[month.month]) for month in MONTHS]
        denial_counts = largest_remainder(month_sizes, payer.denials)
        denial_counts = shift_to_caps(denial_counts, month_sizes)
        denied_claims: list[dict] = []
        for month, count in zip(MONTHS, denial_counts):
            bucket = list(by_month[month.month])
            order = rng.permutation(len(bucket))
            for pick in order[:count]:
                denied_claims.append(bucket[int(pick)])
        if len(denied_claims) != payer.denials:
            raise RuntimeError(f"denial count drifted for {payer.id}")

        labels: list[str] = []
        for code in ACTIVE_CARCS:
            labels.extend([code] * DENIALS_BY_PAYER[payer.id][code])
        order = rng.permutation(len(labels))
        for claim, label_index in zip(denied_claims, order):
            claim["denied"] = True
            claim["carc"] = labels[int(label_index)]
            claim["denial_group"] = "CO"
            claim["worked"] = False


def _period_index(service_date: date) -> int:
    for index, (start, end) in enumerate(PERIODS):
        if start <= service_date <= end:
            return index
    raise RuntimeError(f"{service_date} is outside the trailing twelve months")


def _authorizations(
    appointments: list[dict], claims: list[dict], rng: np.random.Generator
) -> list[dict]:
    missed: dict[tuple[str, int], int] = defaultdict(int)
    for row in appointments:
        if row["status"] in {"no_show", "late_cancel"}:
            missed[(row["patient_id"], _period_index(row["service_date"]))] += row["units"]

    grouped: dict[tuple[str, int], list[dict]] = defaultdict(list)
    for claim in claims:
        if claim["carc"] == "197":
            continue
        grouped[(claim["patient_id"], _period_index(claim["service_date"]))].append(claim)

    patient_meta = {}
    for row in appointments:
        patient_meta[row["patient_id"]] = row

    auths: list[dict] = []
    for patient_id, period_index in sorted(grouped):
        bucket = grouped[(patient_id, period_index)]
        meta = patient_meta[patient_id]
        delivered = sum(claim["units"] for claim in bucket if claim["carc"] != "198")
        exceeded = sum(claim["units"] for claim in bucket if claim["carc"] == "198")
        missed_units = int(missed.get((patient_id, period_index), 0))
        start, end = PERIODS[period_index]
        if exceeded > 0:
            authorized = delivered
            used = delivered + exceeded
            missed_recorded = missed_units
            unbooked = 0
        else:
            weights = np.asarray(UNBOOKED_UNIT_WEIGHTS, dtype=float)
            unbooked = int(rng.choice(list(UNBOOKED_UNIT_CHOICES), p=weights / weights.sum()))
            authorized = delivered + missed_units + unbooked
            used = delivered
            missed_recorded = missed_units
        auth = {
            "auth_id": "",
            "patient_id": patient_id,
            "payer": meta["payer"],
            "payer_category": meta["payer_category"],
            "service_line": meta["service_line"],
            "clinician": meta["clinician"],
            "period_start": start,
            "period_end": end,
            "authorized_units": int(authorized),
            "used_units": int(used),
            "missed_units": int(missed_recorded),
            "unbooked_units": int(unbooked),
            "exceeded_units": int(exceeded),
            "status": "open" if end >= SNAPSHOT else "expired",
        }
        auths.append(auth)
        for claim in bucket:
            claim["auth_id"] = auth  # replaced with the id after ids are assigned

    # Stash the auth dict on the claim temporarily; ids are filled in later.
    for claim in claims:
        if isinstance(claim.get("auth_id"), dict):
            claim["_auth"] = claim["auth_id"]
            claim["auth_id"] = None
    return auths


def _assign_dollars(claims: list[dict], rng: np.random.Generator) -> None:
    month_index = {month.month: index for index, month in enumerate(MONTHS)}
    payer_index = {payer.id: index for index, payer in enumerate(PAYERS)}
    counts = np.zeros((len(PAYERS), len(MONTHS)), dtype=int)
    for claim in claims:
        counts[payer_index[claim["payer_id"]], month_index[claim["month"]]] += 1
    if np.any(counts == 0):
        raise RuntimeError("every payer should have claims in every month")

    base = counts * BILLED_MIN_CENTS
    row_extra = [payer.billed_cents - int(base[i].sum()) for i, payer in enumerate(PAYERS)]
    col_extra = [month.billed_cents - int(base[:, j].sum()) for j, month in enumerate(MONTHS)]
    if any(value < 0 for value in row_extra + col_extra):
        raise RuntimeError("minimum charge does not fit inside a published total")
    room = (BILLED_MAX_CENTS - BILLED_MIN_CENTS) * counts
    extra = integer_matrix(row_extra, col_extra, weights=counts.astype(float))
    if np.any(extra > room):
        raise RuntimeError("a payer-month would have to bill above $240 a claim")
    cell_billed = base + extra

    billed = np.zeros(len(claims), dtype=int)
    grouped: dict[tuple[int, int], list[int]] = defaultdict(list)
    for index, claim in enumerate(claims):
        grouped[(payer_index[claim["payer_id"]], month_index[claim["month"]])].append(index)
    for (payer_i, month_i), indexes in sorted(grouped.items()):
        parts = split_exact(
            int(cell_billed[payer_i, month_i]),
            len(indexes),
            BILLED_MIN_CENTS,
            BILLED_MAX_CENTS,
            rng,
        )
        for index, amount in zip(indexes, parts):
            billed[index] = int(amount)

    denied = np.array([claim["denied"] for claim in claims])
    payer_of = np.array([payer_index[claim["payer_id"]] for claim in claims])
    month_of = np.array([month_index[claim["month"]] for claim in claims])
    paid = _allocate_paid(
        billed,
        denied,
        payer_of,
        month_of,
        [payer.paid_cents for payer in PAYERS],
        [month.paid_cents for month in MONTHS],
    )
    allowed = _allowed_amounts(billed, paid, denied)

    for index, claim in enumerate(claims):
        claim["billed_cents"] = int(billed[index])
        claim["paid_cents"] = int(paid[index])
        claim["allowed_cents"] = int(allowed[index])


def _allocate_paid(
    billed: np.ndarray,
    denied: np.ndarray,
    payer_of: np.ndarray,
    month_of: np.ndarray,
    payer_targets: list[int],
    month_targets: list[int],
) -> np.ndarray:
    low = np.zeros(len(billed), dtype=int)
    high = np.zeros(len(billed), dtype=int)
    paid = np.zeros(len(billed), dtype=int)
    for index, is_denied in enumerate(denied):
        if is_denied:
            continue
        low[index] = int(round(billed[index] * PAID_LOW_RATIO))
        high[index] = int(round(billed[index] * PAID_HIGH_RATIO))
        high[index] = min(high[index], int(billed[index]))
        if high[index] < low[index]:
            high[index] = low[index]
        paid[index] = min(max(int(round(billed[index] * 0.675)), low[index]), high[index])

    for payer_i, target in enumerate(payer_targets):
        indexes = np.where(payer_of == payer_i)[0]
        _distribute(paid, low, high, indexes, target)

    _repair_months(paid, low, high, payer_of, month_of, month_targets)
    return paid


def _distribute(
    paid: np.ndarray,
    low: np.ndarray,
    high: np.ndarray,
    indexes: np.ndarray,
    target: int,
) -> None:
    values = paid[indexes].copy()
    floors = low[indexes]
    caps = high[indexes]
    if int(floors.sum()) > target or int(caps.sum()) < target:
        raise RuntimeError(
            f"paid target {target} is outside [{int(floors.sum())}, {int(caps.sum())}]"
        )
    for _ in range(8):
        diff = target - int(values.sum())
        if diff == 0:
            break
        slack = (caps - values) if diff > 0 else (values - floors)
        if int(slack.sum()) < abs(diff):
            raise RuntimeError("not enough slack to hit the paid target")
        raw = slack.astype(float) / float(slack.sum()) * abs(diff)
        step = np.floor(raw + 1e-9).astype(int)
        left = abs(diff) - int(step.sum())
        order = np.argsort(-(raw - step), kind="mergesort")
        for k in range(left):
            step[int(order[k])] += 1
        step = np.minimum(step, slack.astype(int))
        values = values + step if diff > 0 else values - step
    if int(values.sum()) != target:
        diff = target - int(values.sum())
        guard = 0
        while diff != 0:
            if diff > 0:
                candidates = np.where(values < caps)[0]
                if len(candidates) == 0:
                    raise RuntimeError("paid distribution stuck high")
                pick = int(candidates[np.argmax(caps[candidates] - values[candidates])])
                values[pick] += 1
                diff -= 1
            else:
                candidates = np.where(values > floors)[0]
                if len(candidates) == 0:
                    raise RuntimeError("paid distribution stuck low")
                pick = int(candidates[np.argmax(values[candidates] - floors[candidates])])
                values[pick] -= 1
                diff += 1
            guard += 1
            if guard > abs(target) + 10:
                raise RuntimeError("penny repair took too long")
    paid[indexes] = values


def _repair_months(
    paid: np.ndarray,
    low: np.ndarray,
    high: np.ndarray,
    payer_of: np.ndarray,
    month_of: np.ndarray,
    month_targets: list[int],
) -> None:
    payers = np.unique(payer_of)
    guard = 0
    while True:
        totals = np.array([int(paid[month_of == month].sum()) for month in range(len(month_targets))])
        diff = np.asarray(month_targets) - totals
        if np.all(diff == 0):
            return
        over = int(np.argmin(diff))
        under = int(np.argmax(diff))
        moved = False
        for payer in payers:
            donors = np.where((payer_of == payer) & (month_of == over) & (paid > low))[0]
            receivers = np.where((payer_of == payer) & (month_of == under) & (paid < high))[0]
            if len(donors) == 0 or len(receivers) == 0:
                continue
            donor = int(donors[np.argmax(paid[donors] - low[donors])])
            receiver = int(receivers[np.argmax(high[receivers] - paid[receivers])])
            step = min(
                int(paid[donor] - low[donor]),
                int(high[receiver] - paid[receiver]),
                int(-diff[over]),
                int(diff[under]),
            )
            if step <= 0:
                continue
            paid[donor] -= step
            paid[receiver] += step
            moved = True
            break
        if not moved:
            raise RuntimeError(f"could not match monthly paid totals; gap {diff.tolist()}")
        guard += 1
        if guard > 100000:
            raise RuntimeError("monthly paid repair took too many steps")


def _allowed_amounts(billed: np.ndarray, paid: np.ndarray, denied: np.ndarray) -> np.ndarray:
    allowed = np.zeros(len(billed), dtype=int)
    for index, is_denied in enumerate(denied):
        if is_denied:
            continue
        amount = int(round(paid[index] / PAID_TO_ALLOWED))
        amount = min(amount, int(billed[index]))
        amount = max(amount, int(paid[index]))
        allowed[index] = amount
    return allowed


def _assign_ids(appointments: list[dict], claims: list[dict], authorizations: list[dict]) -> None:
    appointments.sort(key=lambda row: (row["service_date"], row["status"], row["clinician"], row["patient_id"]))
    for index, row in enumerate(appointments, start=1):
        row["appointment_id"] = f"APT-{index:05d}"

    claims.sort(key=lambda row: (row["service_date"], row["patient_id"], row["cpt"], row["clinician"]))
    for index, claim in enumerate(claims, start=1):
        claim["claim_id"] = f"CLM-{index:05d}"
        claim["appointment_id"] = claim["_appointment"]["appointment_id"]

    authorizations.sort(key=lambda row: (row["patient_id"], row["period_start"]))
    for index, auth in enumerate(authorizations, start=1):
        auth["auth_id"] = f"AUTH-{index:04d}"

    for claim in claims:
        auth = claim.get("_auth")
        claim["auth_id"] = None if auth is None else auth["auth_id"]


def _finalize_followup(claims: list[dict], rng: np.random.Generator) -> None:
    """Remit lag and which denials were left unworked, in claim-id order."""
    for claim in claims:
        lag = int(rng.integers(18, 36))
        remit = claim["service_date"] + timedelta(days=lag)
        if remit > SNAPSHOT:
            remit = SNAPSHOT
        claim["remit_date"] = remit
        claim["age_days"] = (SNAPSHOT - remit).days

    denied = [claim for claim in claims if claim["denied"]]
    buckets = {
        "0-30": [],
        "31-60": [],
        "61-90": [],
        "91+": [],
    }
    for claim in denied:
        buckets[_bucket(claim["age_days"])].append(claim)
    for name, group in buckets.items():
        share = UNWORKED_SHARE_BY_BUCKET[name]
        unworked_count = int(round(share * len(group)))
        order = rng.permutation(len(group))
        chosen = {int(order[k]) for k in range(unworked_count)}
        for index, claim in enumerate(group):
            claim["worked"] = index not in chosen


def _bucket(age_days: int) -> str:
    if age_days <= 30:
        return "0-30"
    if age_days <= 60:
        return "31-60"
    if age_days <= 90:
        return "61-90"
    return "91+"


def _patient_frame(appointments: list[dict]) -> pd.DataFrame:
    seen = {}
    for row in appointments:
        seen[row["patient_id"]] = {
            "patient_id": row["patient_id"],
            "service_line": row["service_line"],
            "payer": row["payer"],
            "payer_category": row["payer_category"],
            "clinician": row["clinician"],
        }
    frame = pd.DataFrame(seen.values())
    return frame.sort_values("patient_id", kind="mergesort").reset_index(drop=True)

