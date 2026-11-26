"""Print the headline figures for the default synthetic book."""

from __future__ import annotations

from up4u_audit.analysis import analyze, retired_carc_note
from up4u_audit.formatting import hours_from_units, money, percent
from up4u_audit.generator import generate
from up4u_audit.roi import estimate_roi


def main() -> None:
    book = generate()
    stats = analyze(book)
    roi = estimate_roi(book)
    head = stats["headline"]
    leaks = stats["leaks"]
    print("UP4U.ai synthetic book  ·  seed", head["seed"])
    print(f"Claims                 {head['claims']:,}")
    print(f"Billed                 {money(head['billed_cents'])}")
    print(f"Paid                   {money(head['paid_cents'])}")
    print(f"Net collection         {percent(head['collection_rate'], 1)}")
    print(f"Denial rate            {percent(head['denial_rate'], 1)}  ({head['denied_claims']} claims)")
    print(f"No-show rate           {percent(head['no_show_rate'], 1)}  ({head['no_shows']} of {head['scheduled_appointments']})")
    print(f"Late-cancel rate       {percent(head['late_cancel_rate'], 1)}  ({head['late_cancels']})")
    print(f"Clean-claim yield      {percent(roi['clean_yield'], 1)}")
    print(
        "Illustrative one-time  "
        f"{money(roi['one_time']['total_cents'])}  "
        f"(low {money(roi['one_time']['low_cents'])})"
    )
    print(
        "  denial rework        " + money(roi["one_time"]["denial_rework_cents"])
    )
    print(
        "  open unbooked fill   " + money(roi["one_time"]["open_unbooked_fill_cents"])
    )
    print(
        "Illustrative next year "
        f"{money(roi['annualized']['total_cents'])}  "
        f"(low {money(roi['annualized']['low_cents'])})"
    )
    print(f"Audit fee              {money(roi['audit_fee_cents'])}")
    unused = stats["authorizations"]["totals"]
    print(
        "Unused authorized hrs  "
        f"{unused['unused_hours']:.0f}  "
        f"(open {unused['open_unused_hours']:.0f}, expired {unused['expired_unused_hours']:.0f}, "
        f"never scheduled {hours_from_units(unused['unbooked_units']):.0f})"
    )
    print(retired_carc_note())
    print(roi["caveat"])


if __name__ == "__main__":
    main()
