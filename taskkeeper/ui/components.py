"""Shared row/status widgets for the Chores and One-time tabs.

Real Streamlit widgets throughout (st.checkbox, st.popover) — no raw
HTML/JS. Density comes from `inject_compact_css()`, which targets the
stable `.st-key-*` class Streamlit attaches to any container/widget
given an explicit `key=`.
"""
from __future__ import annotations

from datetime import date
from typing import Callable

import streamlit as st

from ..domain.task import RecurringChore
from .format import format_date_short_fr


def inject_compact_css() -> None:
    st.markdown(
        """
        <style>
        /* -- row density ------------------------------------------------ */
        .st-key-chore_row {
            padding: 0 4px !important;
            border-bottom: 1px solid rgba(49, 51, 63, 0.08);
            line-height: 1.1;
        }
        .st-key-chore_row:hover { background: rgba(49, 51, 63, 0.025); }
        .st-key-chore_row [data-testid="stHorizontalBlock"] {
            gap: 0.4rem !important;
            align-items: center !important;
        }
        .st-key-chore_row [data-testid="stElementContainer"] {
            margin-bottom: 0 !important;
        }
        div[data-testid="stVerticalBlockBorderWrapper"]:has(> div > div.st-key-chore_row) {
            gap: 0rem;
        }

        /* -- header / toolbar rows wrap on narrow screens ---------------- */
        .st-key-chores_header_controls [data-testid="stHorizontalBlock"],
        .st-key-chores_sort_toolbar [data-testid="stHorizontalBlock"] {
            flex-wrap: wrap !important;
            row-gap: 6px !important;
        }

        /* -- text styles -------------------------------------------------- */
        .chore-name-done { text-decoration: line-through; color: #808495; }
        .chore-name-late { color: #bd4043; }
        .chore-name-rescheduled { color: #926c05; }
        .chore-tag {
            font-size: 0.7rem; padding: 0 5px; border-radius: 4px;
            margin-left: 5px; white-space: nowrap;
        }
        .chore-tag-late { color: #bd4043; background: #fff5f5; border: 1px solid #f3caca; }
        .chore-tag-rescheduled { color: #926c05; background: #fffdf3; border: 1px solid #f0e2b8; }
        .chore-duration, .chore-detail { color: #808495; font-size: 0.78rem; white-space: nowrap; }
        .chore-priority-dot {
            display: inline-block; width: 7px; height: 7px; border-radius: 50%;
        }

        /* -- compact reschedule popover ----------------------------------- */
        [class*="st-key-resched_popover_"] [data-testid="stElementContainer"] {
            margin-bottom: 3px !important;
        }
        [class*="st-key-resched_popover_"] [data-testid="stHorizontalBlock"] {
            gap: 0.35rem !important;
        }

        /* -- mobile: shrink further, hide the priority dot, let the row
           wrap instead of squeezing every column unreadably ------------- */
        @media (max-width: 600px) {
            .chore-priority-dot { display: none; }
            .st-key-chore_row { font-size: 0.85em; }
            .st-key-chore_row [data-testid="stHorizontalBlock"] {
                flex-wrap: wrap;
                row-gap: 2px;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _row_status(chore: RecurringChore, current_date: date) -> str:
    if chore.is_completed_on(current_date):
        return "done"
    if chore.is_manually_rescheduled() and chore.due_date != current_date:
        return "rescheduled"
    if chore.due_date and chore.due_date < current_date and not chore.is_completed():
        return "late"
    return "todo"


def _priority_tier_color(priority: float) -> str:
    if priority >= 14:
        return "#bd4043"
    if priority >= 8:
        return "#d9a441"
    return "#a3a8b8"


def render_task_row(
    chore: RecurringChore,
    current_date: date,
    *,
    show_details: bool,
    next_due_date: date | None,
    on_toggle: Callable[[str], None],
    on_reschedule_today: Callable[[str], None],
    on_reschedule_weekend: Callable[[str], None],
    on_reschedule_next_due: Callable[[str], None],
    on_reschedule_date: Callable[[str, date], None],
    on_cancel: Callable[[str], None],
) -> None:
    """One compact row. In detail mode (`show_details=True`) two extra
    columns appear: exact priority and the due/done date — otherwise
    only the priority-tier dot and status tag carry that information."""
    status = _row_status(chore, current_date)

    row = st.container(key=f"chore_row_{chore.id}")
    with row:
        if show_details:
            ratios = [0.05, 0.04, 0.04, 0.36, 0.09, 0.13, 0.13, 0.09]
        else:
            ratios = [0.06, 0.05, 0.05, 0.58, 0.14, 0.10]
        cols = st.columns(ratios, gap="small", vertical_alignment="center")
        i = iter(cols)

        with next(i):
            st.checkbox(
                "done", value=status == "done", key=f"chk_{chore.id}",
                label_visibility="collapsed",
                on_change=lambda cid=chore.id: on_toggle(cid),
                disabled=status == "rescheduled",
            )

        with next(i):
            st.markdown(
                f"<span class='chore-priority-dot' "
                f"style='background:{_priority_tier_color(chore.priority)};'></span>",
                unsafe_allow_html=True,
            )

        with next(i):
            st.markdown(f"<span>{chore.category.icon}</span>", unsafe_allow_html=True)

        with next(i):
            name_class = {
                "done": "chore-name-done",
                "late": "chore-name-late",
                "rescheduled": "chore-name-rescheduled",
            }.get(status, "")
            tag_html = ""
            if status == "late":
                tag_html = "<span class='chore-tag chore-tag-late'>en retard</span>"
            elif status == "rescheduled":
                tag_html = "<span class='chore-tag chore-tag-rescheduled'>reporté</span>"
            st.markdown(f"<span class='{name_class}'>{chore.name}</span>{tag_html}", unsafe_allow_html=True)

        if show_details:
            with next(i):
                st.markdown(f"<span class='chore-detail'>{chore.priority:.1f}</span>", unsafe_allow_html=True)
            with next(i):
                shown_date = chore.done_date if status == "done" else chore.due_date
                label = format_date_short_fr(shown_date) if shown_date else "—"
                st.markdown(f"<span class='chore-detail'>{label}</span>", unsafe_allow_html=True)

        with next(i):
            st.markdown(f"<span class='chore-duration'>{chore.duration} min</span>", unsafe_allow_html=True)

        with next(i):
            with st.popover("⋯", width="content"):
                body = st.container(key=f"resched_popover_{chore.id}")
                with body:
                    quick = st.columns(2, gap="small")
                    quick[0].button(
                        "📅 Aujourd'hui", key=f"resched_today_{chore.id}", width="stretch",
                        on_click=lambda cid=chore.id: on_reschedule_today(cid),
                    )
                    quick[1].button(
                        "🛌 Week-end", key=f"resched_weekend_{chore.id}", width="stretch",
                        on_click=lambda cid=chore.id: on_reschedule_weekend(cid),
                    )
                    next_label = f"⏭ {format_date_short_fr(next_due_date)}" if next_due_date else "⏭ Prochaine échéance"
                    st.button(
                        next_label, key=f"resched_next_{chore.id}", width="stretch",
                        on_click=lambda cid=chore.id: on_reschedule_next_due(cid),
                    )
                    pick = st.columns([0.68, 0.32], gap="small")
                    picked = pick[0].date_input(
                        "date", value=current_date, key=f"resched_pick_{chore.id}",
                        label_visibility="collapsed",
                    )
                    pick[1].button(
                        "OK", key=f"resched_pick_btn_{chore.id}", width="stretch",
                        on_click=lambda cid=chore.id, d=picked: on_reschedule_date(cid, d),
                    )
                    st.divider()
                    st.button(
                        "✕ Annuler", key=f"cancel_{chore.id}", width="stretch", type="tertiary",
                        on_click=lambda cid=chore.id: on_cancel(cid),
                    )
