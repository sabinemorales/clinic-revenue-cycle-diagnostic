"""Streamlit demo of the UP4U.ai No-Show Recovery Audit.

Run from the repository root:

    streamlit run app.py
"""

from __future__ import annotations

import html
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

import altair as alt
import pandas as pd
import streamlit as st

from up4u_audit.analysis import analyze, retired_carc_note
from up4u_audit.formatting import hours_from_units, money, percent
from up4u_audit.generator import AuditBook, generate
from up4u_audit.plan import weekly_actions
from up4u_audit.roi import RoiAssumptions, estimate_roi

BANNER = "Synthetic data — illustrative only"
CLINIC = "Sample Pediatric Therapy Clinic"

PALETTE = {
    "No-shows": "#B8613A",
    "Late cancels": "#C4922A",
    "Denials": "#2F5D62",
    "Unused, still open": "#3E6B4F",
    "Unused, expired": "#6E3B3B",
    "No-show rate": "#B8613A",
    "Late-cancel rate": "#C4922A",
    "All denied": "#2F5D62",
    "Unworked": "#6E3B3B",
    "Billed": "#243E36",
    "Paid": "#B8613A",
}

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Source+Sans+3:wght@400;600;700&family=Source+Serif+4:opsz,wght@8..60,560;8..60,650&display=swap');

html, body, [class*="css"] {
  font-family: "Source Sans 3", "Segoe UI", Helvetica, Arial, sans-serif;
}
h1, h2, h3 {
  font-family: "Source Serif 4", Georgia, "Times New Roman", serif;
  letter-spacing: -0.02em;
  color: #1C2B29;
}
.synth-banner {
  background: #243E36;
  color: #F7F4EF;
  padding: 0.65rem 1rem;
  border-radius: 8px;
  font-weight: 700;
  letter-spacing: 0.01em;
  margin: 0 0 0.9rem 0;
}
section[data-testid="stSidebar"] .synth-banner {
  font-size: 0.86rem;
  line-height: 1.35;
  margin-top: 0.4rem;
}
.brand-kicker {
  color: #B8613A;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  font-size: 0.78rem;
  margin: 0 0 0.15rem 0;
}
.lede {
  color: #3E4A46;
  font-size: 1.02rem;
  margin-top: 0;
}
.note {
  color: #3E4A46;
  font-size: 0.92rem;
}
.caveat {
  background: #F3E6D8;
  border-left: 4px solid #B8613A;
  padding: 0.8rem 1rem;
  border-radius: 6px;
  color: #1C2B29;
}
.week-card {
  border: 1px solid #E0D6C8;
  border-radius: 10px;
  padding: 0.2rem 1.1rem 0.4rem 1.1rem;
  background: #FFFCF7;
  margin-bottom: 0.75rem;
}
.week-num {
  color: #B8613A;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  font-size: 0.75rem;
  margin-bottom: 0;
}
.week-card h3 { margin-bottom: 0.2rem; }
.intent { color: #3E4A46; margin-top: 0; }
.foot {
  color: #5C6B66;
  font-size: 0.85rem;
  margin-top: 1.5rem;
}
table.assumptions {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.92rem;
  margin: 0.2rem 0 0.6rem 0;
}
table.assumptions th {
  text-align: left;
  color: #5C6B66;
  font-weight: 600;
  padding: 0.35rem 0.55rem 0.45rem 0;
  border-bottom: 1px solid #C9BEB0;
}
table.assumptions td {
  vertical-align: top;
  padding: 0.55rem 0.7rem 0.55rem 0;
  border-bottom: 1px solid #E4DDD2;
  color: #1C2B29;
}
table.assumptions td.value {
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
  width: 16rem;
}
div[data-testid="stMetricValue"] { color: #1C2B29; }
header[data-testid="stHeader"], #MainMenu, footer { display: none; }
.block-container { padding-top: 1.4rem; max-width: 1180px; }
</style>
"""


@st.cache_data(show_spinner="Building the synthetic book…")
def load_book(seed: int):
    book = generate(seed)
    return book.appointments, book.claims, book.authorizations, book.patients, book.seed, book.snapshot


def book_from_cache(seed: int) -> AuditBook:
    appointments, claims, authorizations, patients, stored_seed, snapshot = load_book(seed)
    return AuditBook(appointments, claims, authorizations, patients, stored_seed, snapshot)


def render_banner() -> None:
    st.markdown(f'<div class="synth-banner">{BANNER}</div>', unsafe_allow_html=True)


def main() -> None:
    st.set_page_config(
        page_title="UP4U.ai — No-Show Recovery Audit",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(CSS, unsafe_allow_html=True)
    render_banner()

    book = book_from_cache(7)
    stats = analyze(book)
    view = st.sidebar.radio("View", ["Revenue leak map", "Weekly action plan"], label_visibility="visible")
    st.sidebar.markdown(f'<div class="synth-banner">{BANNER}</div>', unsafe_allow_html=True)
    st.sidebar.markdown("**UP4U.ai**")
    st.sidebar.caption("No-Show Recovery Audit · $1,200 fixed fee · 10 business days")
    st.sidebar.caption(f"{CLINIC}. Seed {book.seed}. Snapshot {book.snapshot.isoformat()}.")

    if view == "Revenue leak map":
        render_leak_map(stats)
    else:
        assumptions = assumption_controls()
        render_action_plan(book, stats, assumptions)

    st.markdown(
        '<p class="foot">Sabine Morales, UP4U.ai · Synthetic book for demonstration. '
        "No real clinic and no patient information.</p>",
        unsafe_allow_html=True,
    )


def render_leak_map(stats: dict) -> None:
    head = stats["headline"]
    st.markdown('<p class="brand-kicker">UP4U.ai · No-Show Recovery Audit</p>', unsafe_allow_html=True)
    st.title("Revenue leak map")
    st.markdown(
        f'<p class="lede">{CLINIC} · ABA, speech, occupational therapy, and physical therapy · '
        f"trailing 12 months ending {_long_date(head['snapshot'])}.</p>",
        unsafe_allow_html=True,
    )
    st.caption(
        "Gross size of each leak in this book. The weekly action plan is where the assumptions live. "
        + stats["leaks"]["note"]
    )

    metrics = st.columns(5)
    metrics[0].metric("Billed", money(head["billed_cents"]))
    metrics[1].metric("Paid", money(head["paid_cents"]))
    metrics[2].metric("Net collection", percent(head["collection_rate"], 1))
    metrics[3].metric("Denial rate", percent(head["denial_rate"], 1))
    metrics[4].metric("No-show rate", percent(head["no_show_rate"], 1))

    leaks = stats["leaks"]
    chart_rows = pd.DataFrame(
        [
            {
                "Leak": "No-shows",
                "Dollars": leaks["no_show"]["illustrative_cents"] / 100,
                "Kind": "Scheduled capacity not delivered",
            },
            {
                "Leak": "Late cancels",
                "Dollars": leaks["late_cancel"]["illustrative_cents"] / 100,
                "Kind": "Scheduled capacity not delivered",
            },
            {
                "Leak": "Denials",
                "Dollars": leaks["denials"]["expected_collection_cents"] / 100,
                "Kind": "Expected collection, using this book's clean-claim yield",
            },
            {
                "Leak": "Unused, still open",
                "Dollars": leaks["unused_authorizations"]["open_illustrative_cents"] / 100,
                "Kind": "Authorized units not billed, authorization still open",
            },
            {
                "Leak": "Unused, expired",
                "Dollars": leaks["unused_authorizations"]["expired_illustrative_cents"] / 100,
                "Kind": "Authorized units not billed, authorization already ended",
            },
        ]
    )
    st.subheader("Where the dollars sit")
    st.altair_chart(horizontal_bars(chart_rows, "Leak", "Dollars", "Illustrative dollars"), width="stretch")
    st.caption(
        "No-shows and late cancels are capacity that was scheduled and not delivered, valued at this book's "
        "average paid amount per paid unit. Denials are expected collection: denied charges times the clean-claim yield, "
        "not a recovery estimate. Unused hours are authorized units that were not billed. Missed visits also sit in the "
        "attendance rows, and expired hours have already lapsed. These amounts are not added together."
    )
    with st.expander("How each figure is valued"):
        st.markdown(f"**No-shows.** {leaks['no_show']['definition']}")
        st.markdown(f"**Late cancels.** {leaks['late_cancel']['definition']}")
        st.markdown(f"**Denials.** {leaks['denials']['definition']}")
        st.markdown(f"**Unused authorizations.** {leaks['unused_authorizations']['definition']}")
        st.markdown(f"**Unworked denials.** {leaks['unworked_denials']['definition']}")

    left, right = st.columns(2)
    with left:
        st.subheader("Denials by CARC")
        denial_table(stats["denials"])
        st.caption(retired_carc_note())
    with right:
        st.subheader("No-show and late cancel by weekday")
        st.altair_chart(weekday_chart(stats["attendance"]["by_weekday"]), width="stretch")
        st.caption(
            f"Late-cancel rate overall is {percent(head['late_cancel_rate'], 1)}. "
            "Late cancels were not on the sample workbook; they are part of this book so the two rates can be compared. "
            "Monday and Friday remain the high no-show days, as in the workbook."
        )

    left, right = st.columns(2)
    with left:
        st.subheader("Denial rate by payer")
        payer_table(stats["payers"])
    with right:
        st.subheader("Unworked denials by age")
        st.altair_chart(aging_chart(stats["aging"]), width="stretch")
        unworked = leaks["unworked_denials"]
        st.caption(
            f"{unworked['claims']} of {leaks['denials']['claims']} denied claims are unworked, "
            f"{money(unworked['billed_cents'])} billed. "
            + unworked["definition"]
        )

    st.subheader("Authorizations")
    auth_table(stats["authorizations"]["by_service_line"])
    totals = stats["authorizations"]["totals"]
    st.caption(
        f"{totals['authorizations']} authorizations. "
        f"{totals['unused_hours']:.0f} unused hours "
        f"({totals['open_unused_hours']:.0f} still open, {totals['expired_unused_hours']:.0f} expired), "
        f"of which {hours_from_units(totals['unbooked_units']):.0f} hours were never scheduled. "
        "A unit is 15 minutes. Visit length by CPT is a generator setting."
    )

    with st.expander("Monthly billed and paid"):
        st.altair_chart(monthly_chart(stats["months"]), width="stretch")
        st.caption("Paid divided by billed, including contractual differences and denials. This is the workbook's monthly shape, matched to the cent.")

    with st.expander("Attendance by clinician and service line"):
        clinician = stats["attendance"]["by_clinician"].copy()
        st.dataframe(
            rate_frame(clinician, "clinician"),
            hide_index=True,
            width="stretch",
            column_config=_rate_columns(),
        )
        service = stats["attendance"]["by_service_line"].copy()
        st.dataframe(
            rate_frame(service, "service_line"),
            hide_index=True,
            width="stretch",
            column_config=_rate_columns(),
        )


def render_action_plan(book, stats: dict, assumptions: RoiAssumptions) -> None:
    head = stats["headline"]
    estimate = estimate_roi(book, assumptions)
    st.markdown('<p class="brand-kicker">UP4U.ai · No-Show Recovery Audit</p>', unsafe_allow_html=True)
    st.title("Weekly action plan")
    st.markdown(
        f'<p class="lede">Four weeks of work for {CLINIC}, ordered by what can still be touched. '
        "Counts come from the book. Dollars come from the assumptions.</p>",
        unsafe_allow_html=True,
    )

    one, low, year, year_low, fee = st.columns(5)
    one.metric("One-time, base", money(estimate["one_time"]["total_cents"]))
    low.metric("One-time, low", money(estimate["one_time"]["low_cents"]))
    year.metric("Next year, base", money(estimate["annualized"]["total_cents"]))
    year_low.metric("Next year, low", money(estimate["annualized"]["low_cents"]))
    fee.metric("Audit fee", money(estimate["audit_fee_cents"]))
    st.caption(
        f"One-time is unworked-denial rework ({money(estimate['one_time']['denial_rework_cents'])}) "
        f"plus still-open hours that were never scheduled ({money(estimate['one_time']['open_unbooked_fill_cents'])}). "
        f"Next year is a {assumptions.horizon_months}-month capacity illustration if missed units fall by the assumed rates "
        f"and the book repeats. Low is {percent(assumptions.low_factor, 1)} of those dollars. "
        f"Net of the fee, the one-time base is {money(estimate['one_time']['net_of_fee_cents'])} "
        f"and the low case is {money(estimate['one_time']['low_net_of_fee_cents'])}."
    )
    st.markdown(f'<div class="caveat">{html.escape(estimate["caveat"])}</div>', unsafe_allow_html=True)

    st.subheader("The four weeks")
    for action in weekly_actions(book, assumptions):
        items = "".join(f"<li>{html.escape(line)}</li>" for line in action["lines"])
        st.markdown(
            f"""
            <div class="week-card">
              <p class="week-num">Week {action['week']}</p>
              <h3>{html.escape(action['title'])}</h3>
              <p class="intent">{html.escape(action['intent'])}</p>
              <ul>{items}</ul>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.subheader("What the one-time estimate is made of")
    carc = pd.DataFrame(estimate["by_carc"])
    carc_view = pd.DataFrame(
        {
            "Code": carc["code"],
            "Reason": carc["short_label"],
            "Unworked claims": carc["unworked_claims"],
            "Inside window": carc["inside_window_claims"],
            "Base": carc["rework_cents"] / 100,
            "Low": carc["low_rework_cents"] / 100,
        }
    )
    st.dataframe(
        carc_view,
        hide_index=True,
        width="stretch",
        column_config={
            "Base": st.column_config.NumberColumn(format="$%.2f"),
            "Low": st.column_config.NumberColumn(format="$%.2f"),
        },
    )
    st.caption(
        "Rework uses only unworked denials. Inside the appeal window the code's yield applies in full; "
        "older remittances keep the outside-window share of that yield. "
        f"Both are then multiplied by this book's clean-claim yield of {percent(estimate['clean_yield'], 1)} "
        "(paid ÷ billed on claims that were not denied)."
    )

    st.subheader("Assumptions")
    st.markdown(_assumptions_html(estimate["assumptions"]), unsafe_allow_html=True)
    st.caption(
        f"Book snapshot {head['snapshot'].isoformat()}, seed {head['seed']}. "
        "Changing a slider rebuilds the estimate. It does not change the claims."
    )


def assumption_controls() -> RoiAssumptions:
    defaults = RoiAssumptions()
    with st.sidebar.expander("Adjust the assumptions"):
        st.caption("Rates are assumptions. The low case stays at half of whatever the sliders produce.")
        window = st.slider("Appeal window (days)", 30, 180, defaults.appeal_window_days)
        outside = st.slider("Outside-window share of the yield (%)", 0, 100, int(defaults.outside_window_multiplier * 100))
        yield_4 = st.slider("CARC 4 yield (%)", 0, 100, int(defaults.rework_yield_4 * 100))
        yield_197 = st.slider("CARC 197 yield (%)", 0, 100, int(defaults.rework_yield_197 * 100))
        yield_198 = st.slider("CARC 198 yield (%)", 0, 100, int(defaults.rework_yield_198 * 100))
        yield_27 = st.slider("CARC 27 yield (%)", 0, 100, int(defaults.rework_yield_27 * 100))
        yield_50 = st.slider("CARC 50 yield (%)", 0, 100, int(defaults.rework_yield_50 * 100))
        yield_29 = st.slider("CARC 29 yield (%)", 0, 100, int(defaults.rework_yield_29 * 100))
        no_show = st.slider("No-show reduction (%)", 0, 100, int(defaults.no_show_relative_reduction * 100))
        late = st.slider("Late-cancel reduction (%)", 0, 100, int(defaults.late_cancel_relative_reduction * 100))
        fill = st.slider("Open unbooked fill rate (%)", 0, 100, int(defaults.open_unbooked_fill_rate * 100))
    return RoiAssumptions(
        appeal_window_days=window,
        outside_window_multiplier=outside / 100,
        rework_yield_4=yield_4 / 100,
        rework_yield_197=yield_197 / 100,
        rework_yield_198=yield_198 / 100,
        rework_yield_27=yield_27 / 100,
        rework_yield_50=yield_50 / 100,
        rework_yield_29=yield_29 / 100,
        no_show_relative_reduction=no_show / 100,
        late_cancel_relative_reduction=late / 100,
        open_unbooked_fill_rate=fill / 100,
    )


def denial_table(frame: pd.DataFrame) -> None:
    current = frame[~frame["retired"]].copy()
    view = pd.DataFrame(
        {
            "Code": current["code"],
            "Reason": current["short_label"],
            "Claims": current["claims"],
            "Share": current["share_of_denials"],
            "Billed": current["billed_cents"] / 100,
        }
    )
    st.dataframe(
        view,
        hide_index=True,
        width="stretch",
        column_config={
            "Share": st.column_config.NumberColumn(format="percent"),
            "Billed": st.column_config.NumberColumn(format="$%.2f"),
        },
    )
    with st.expander("Official X12 wording"):
        for row in current.itertuples(index=False):
            st.markdown(f"**{row.code}.** {row.description}")


def payer_table(frame: pd.DataFrame) -> None:
    view = pd.DataFrame(
        {
            "Payer": frame["payer"],
            "Category": frame["payer_category"],
            "Claims": frame["claims"],
            "Billed": frame["billed_cents"] / 100,
            "Paid": frame["paid_cents"] / 100,
            "Denial rate": frame["denial_rate"],
        }
    )
    st.dataframe(
        view,
        hide_index=True,
        width="stretch",
        column_config={
            "Billed": st.column_config.NumberColumn(format="$%.2f"),
            "Paid": st.column_config.NumberColumn(format="$%.2f"),
            "Denial rate": st.column_config.NumberColumn(format="percent"),
        },
    )


def auth_table(frame: pd.DataFrame) -> None:
    view = pd.DataFrame(
        {
            "Service line": frame["service_line"],
            "Authorizations": frame["authorizations"],
            "Authorized hours": frame["authorized_hours"],
            "Unused hours": frame["unused_hours"],
            "Never scheduled": frame["unbooked_hours"],
            "Open unused hours": frame["open_unused_hours"],
            "Expired unused hours": frame["expired_unused_hours"],
        }
    )
    st.dataframe(
        view,
        hide_index=True,
        width="stretch",
        column_config={
            "Authorized hours": st.column_config.NumberColumn(format="%.0f"),
            "Unused hours": st.column_config.NumberColumn(format="%.0f"),
            "Never scheduled": st.column_config.NumberColumn(format="%.0f"),
            "Open unused hours": st.column_config.NumberColumn(format="%.0f"),
            "Expired unused hours": st.column_config.NumberColumn(format="%.0f"),
        },
    )


def rate_frame(frame: pd.DataFrame, key: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            key.replace("_", " ").title(): frame[key],
            "Appointments": frame["appointments"],
            "No-show rate": frame["no_show_rate"],
            "Late-cancel rate": frame["late_cancel_rate"],
        }
    )


def _rate_columns() -> dict:
    return {
        "No-show rate": st.column_config.NumberColumn(format="percent"),
        "Late-cancel rate": st.column_config.NumberColumn(format="percent"),
    }


def _long_date(value) -> str:
    return f"{value.strftime('%B')} {value.day}, {value.year}"


def _assumptions_html(rows: list[dict]) -> str:
    body = []
    for row in rows:
        body.append(
            "<tr>"
            f"<td>{html.escape(row['assumption'])}</td>"
            f"<td class='value'>{html.escape(row['value'])}</td>"
            f"<td>{html.escape(row['role'])}</td>"
            "</tr>"
        )
    return (
        "<table class='assumptions'><thead><tr>"
        "<th>Assumption</th><th>Value</th><th>Role</th>"
        "</tr></thead><tbody>"
        + "".join(body)
        + "</tbody></table>"
    )


def horizontal_bars(frame: pd.DataFrame, category: str, value: str, value_title: str) -> alt.Chart:
    order = frame[category].tolist()
    return (
        alt.Chart(frame)
        .mark_bar(cornerRadiusEnd=3, height=22)
        .encode(
            x=alt.X(f"{value}:Q", title=value_title, axis=alt.Axis(format="$,.0f")),
            y=alt.Y(f"{category}:N", sort=order, title=None, axis=alt.Axis(labelLimit=160)),
            color=alt.Color(
                f"{category}:N",
                scale=alt.Scale(domain=order, range=[PALETTE[name] for name in order]),
                legend=None,
            ),
            tooltip=[
                alt.Tooltip(f"{category}:N", title="Leak"),
                alt.Tooltip(f"{value}:Q", title="Dollars", format="$,.2f"),
                alt.Tooltip("Kind:N", title="What this counts"),
            ],
        )
        .properties(height=280)
        .configure_view(stroke=None)
        .configure_axis(labelColor="#1C2B29", titleColor="#1C2B29", gridColor="#E4DDD2")
    )


def weekday_chart(frame: pd.DataFrame) -> alt.Chart:
    long = frame.melt(
        id_vars=["weekday"],
        value_vars=["no_show_rate", "late_cancel_rate"],
        var_name="measure",
        value_name="rate",
    )
    long["measure"] = long["measure"].map(
        {"no_show_rate": "No-show rate", "late_cancel_rate": "Late-cancel rate"}
    )
    long["percent"] = long["rate"] * 100
    order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    return (
        alt.Chart(long)
        .mark_bar(cornerRadiusEnd=2)
        .encode(
            x=alt.X("weekday:N", sort=order, title=None),
            y=alt.Y("percent:Q", title="Percent of appointments", axis=alt.Axis(format=".0f")),
            color=alt.Color(
                "measure:N",
                title=None,
                scale=alt.Scale(
                    domain=["No-show rate", "Late-cancel rate"],
                    range=[PALETTE["No-show rate"], PALETTE["Late-cancel rate"]],
                ),
            ),
            xOffset="measure:N",
            tooltip=[
                alt.Tooltip("weekday:N", title="Day"),
                alt.Tooltip("measure:N", title=""),
                alt.Tooltip("percent:Q", title="Percent", format=".1f"),
            ],
        )
        .properties(height=320)
        .configure_view(stroke=None)
        .configure_axis(labelColor="#1C2B29", titleColor="#1C2B29", gridColor="#E4DDD2")
        .configure_legend(labelColor="#1C2B29", orient="bottom")
    )


def aging_chart(frame: pd.DataFrame) -> alt.Chart:
    long = frame.melt(
        id_vars=["bucket"],
        value_vars=["denied_billed_cents", "unworked_billed_cents"],
        var_name="series",
        value_name="cents",
    )
    long["series"] = long["series"].map(
        {"denied_billed_cents": "All denied", "unworked_billed_cents": "Unworked"}
    )
    long["dollars"] = long["cents"] / 100
    return (
        alt.Chart(long)
        .mark_bar(cornerRadiusEnd=2)
        .encode(
            x=alt.X("bucket:N", sort=list(frame["bucket"]), title="Days since remittance"),
            y=alt.Y("dollars:Q", title="Billed dollars", axis=alt.Axis(format="$,.0f")),
            color=alt.Color(
                "series:N",
                title=None,
                scale=alt.Scale(domain=["All denied", "Unworked"], range=[PALETTE["All denied"], PALETTE["Unworked"]]),
            ),
            xOffset="series:N",
            tooltip=[
                alt.Tooltip("bucket:N", title="Age"),
                alt.Tooltip("series:N", title=""),
                alt.Tooltip("dollars:Q", title="Billed", format="$,.2f"),
            ],
        )
        .properties(height=320)
        .configure_view(stroke=None)
        .configure_axis(labelColor="#1C2B29", titleColor="#1C2B29", gridColor="#E4DDD2")
        .configure_legend(labelColor="#1C2B29", orient="bottom")
    )


def monthly_chart(frame: pd.DataFrame) -> alt.Chart:
    long = frame.melt(id_vars=["month"], value_vars=["billed_cents", "paid_cents"], var_name="series", value_name="cents")
    long["series"] = long["series"].map({"billed_cents": "Billed", "paid_cents": "Paid"})
    long["dollars"] = long["cents"] / 100
    return (
        alt.Chart(long)
        .mark_line(point=True)
        .encode(
            x=alt.X("month:N", sort=list(frame["month"]), title=None),
            y=alt.Y("dollars:Q", title="Dollars", axis=alt.Axis(format="$,.0f")),
            color=alt.Color(
                "series:N",
                title=None,
                scale=alt.Scale(domain=["Billed", "Paid"], range=[PALETTE["Billed"], PALETTE["Paid"]]),
            ),
            tooltip=[
                alt.Tooltip("month:N", title="Month"),
                alt.Tooltip("series:N", title=""),
                alt.Tooltip("dollars:Q", format="$,.2f"),
            ],
        )
        .properties(height=280)
        .configure_view(stroke=None)
        .configure_axis(labelColor="#1C2B29", titleColor="#1C2B29", gridColor="#E4DDD2")
        .configure_legend(labelColor="#1C2B29", orient="bottom")
    )


if __name__ == "__main__":
    main()
