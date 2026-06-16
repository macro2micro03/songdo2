"""Performance timing instrumentation.

Activated via Streamlit secrets:
    DEBUG_TIMING = true

Usage:
    from shared.timing import measure, db_timer, clear_timings, render_panel, is_enabled

    @measure("dashboard.compute_kpi")
    def compute_kpi(...): ...

    with db_timer("requests.select_today"):
        rows = con.table("requests").select(...).execute()

    # In app.py:
    clear_timings()    # at top of each rerun
    render_panel()     # at end (renders sidebar expander)

When DEBUG_TIMING is false (default), all calls are zero-overhead no-ops.
"""
from __future__ import annotations

import functools
import time
from typing import Any, Callable, Optional

import streamlit as st


# ── secrets toggle ────────────────────────────────────────────────────────

def is_enabled() -> bool:
    """Check if performance timing is active.

    Looks at Streamlit secrets first (DEBUG_TIMING), then env-var fallback.
    Cached per-session to avoid repeated lookups.
    """
    cached = st.session_state.get("__debug_timing_enabled")
    if cached is not None:
        return cached
    raw = st.secrets.get("DEBUG_TIMING", "false")
    enabled = str(raw).strip().lower() in ("true", "1", "yes", "on")
    st.session_state["__debug_timing_enabled"] = enabled
    return enabled


# ── per-rerun timings storage ─────────────────────────────────────────────

def _ensure_storage() -> None:
    st.session_state.setdefault("__timings", [])


def clear_timings() -> None:
    """Reset timings at the very top of each rerun. Safe to call always."""
    if not is_enabled():
        return
    st.session_state["__timings"] = []
    st.session_state["__timing_start"] = time.perf_counter()


def record(label: str, duration_ms: float, kind: str = "func") -> None:
    """Append one timing entry."""
    if not is_enabled():
        return
    _ensure_storage()
    st.session_state["__timings"].append({
        "label": label, "duration_ms": float(duration_ms), "kind": kind,
    })


# ── decorator ─────────────────────────────────────────────────────────────

def measure(label: Optional[str] = None) -> Callable:
    """Function timing decorator. Zero overhead when DEBUG_TIMING is false."""
    def decorator(fn: Callable) -> Callable:
        fn_label = label or f"{fn.__module__}.{fn.__name__}"

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            if not is_enabled():
                return fn(*args, **kwargs)
            start = time.perf_counter()
            try:
                return fn(*args, **kwargs)
            finally:
                record(fn_label, (time.perf_counter() - start) * 1000.0)
        return wrapper
    return decorator


# ── context manager for explicit DB / IO sections ────────────────────────

class db_timer:
    """Context manager. ``with db_timer("requests.list_today"): ...``."""

    __slots__ = ("label", "kind", "_t")

    def __init__(self, label: str, kind: str = "db") -> None:
        self.label = label
        self.kind = kind
        self._t = 0.0

    def __enter__(self) -> "db_timer":
        if is_enabled():
            self._t = time.perf_counter()
        return self

    def __exit__(self, *exc: Any) -> None:
        if is_enabled():
            record(f"db:{self.label}", (time.perf_counter() - self._t) * 1000.0,
                   kind=self.kind)


# ── sidebar panel renderer ────────────────────────────────────────────────

def render_panel() -> None:
    """Render the timing summary in the sidebar. Call ONCE at end of rerun."""
    if not is_enabled():
        return

    timings = st.session_state.get("__timings", [])
    start = st.session_state.get("__timing_start")
    total_ms = (time.perf_counter() - start) * 1000.0 if start else 0.0

    # Aggregate by label
    agg: dict = {}
    db_total = 0.0
    db_count = 0
    for t in timings:
        a = agg.setdefault(t["label"], {"count": 0, "total": 0.0, "kind": t["kind"]})
        a["count"] += 1
        a["total"] += t["duration_ms"]
        if t["kind"] == "db":
            db_total += t["duration_ms"]
            db_count += 1
    sorted_items = sorted(agg.items(), key=lambda kv: -kv[1]["total"])

    with st.sidebar:
        with st.expander("⏱ DEBUG_TIMING", expanded=True):
            st.markdown(
                f"**Total render: `{total_ms:.0f} ms`**\n\n"
                f"DB calls: **{db_count}** (`{db_total:.0f} ms` total)\n\n"
                f"Tracked entries: {len(timings)}"
            )
            if not sorted_items:
                st.caption("(no timed functions yet — add @measure or db_timer)")
                return
            st.markdown("**Top by total time**")
            for label, stats in sorted_items[:20]:
                avg = stats["total"] / max(stats["count"], 1)
                badge = "🗄️" if stats["kind"] == "db" else "•"
                st.caption(
                    f"{badge} `{stats['total']:7.0f}ms`  "
                    f"({stats['count']}×, avg {avg:.0f}ms)  — {label}"
                )
