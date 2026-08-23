"""The 'Timer' tab: a simple play/pause/reset stopwatch.

Backed by TimerService (SQLite via SettingsStore), not raw
st.session_state — the ticking display is still a Streamlit fragment
(same run_every pattern as the original app) so only this small piece
of the page re-renders every tick.
"""
from __future__ import annotations

import streamlit as st

from ..services.timer_service import TimerService

_TICK_SECONDS = 1.0


def _format(total_seconds: int) -> str:
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def _timer_display(service: TimerService) -> None:
    st.markdown(
        f"<h1 style='text-align:center; font-size: 4rem; margin: 0.3em 0;'>{_format(service.elapsed_seconds())}</h1>",
        unsafe_allow_html=True,
    )


@st.fragment(run_every=_TICK_SECONDS)
def _live_clock(service: TimerService) -> None:
    if not service.is_running():
        return
    _timer_display(service)


def render(service: TimerService) -> None:
    st.markdown("### Timer")

    with st.container(horizontal_alignment="center", border=True, width="content"):
        if service.is_running():
            _live_clock(service)
        else:
            _timer_display(service)

        with st.container(horizontal=True, horizontal_alignment="center", width="content"):
            if service.is_running():
                st.button("⏸ Pause", on_click=service.pause, width="stretch")
            else:
                st.button("▶️ Play", on_click=service.start, width="stretch")
            st.button("⏹ Reset", on_click=service.reset, width="stretch")
