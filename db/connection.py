"""Database connection — Supabase client factory (with optional sqlite fallback for dev).

When ``DEBUG_TIMING=true`` is set in Streamlit secrets, the returned client is
wrapped with a thin proxy that measures every ``.execute()`` call and feeds the
duration into ``shared.timing``. The proxy short-circuits when timing is
disabled, so production cost is negligible.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import streamlit as st
from supabase import Client, create_client

from shared.helpers import ensure_dir


# ── Timed proxy: wraps Supabase client to record every .execute() call ───

class _TimedQueryBuilder:
    """Proxies a postgrest builder, intercepting .execute() to record timings."""

    __slots__ = ("_b", "_label")

    def __init__(self, builder: Any, label: str) -> None:
        self._b = builder
        self._label = label

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._b, name)

        if name == "execute":
            def timed_execute(*args, **kwargs):
                # Lazy import to avoid circular dep at module load
                from shared.timing import is_enabled, record
                if not is_enabled():
                    return attr(*args, **kwargs)
                start = time.perf_counter()
                try:
                    return attr(*args, **kwargs)
                finally:
                    record(f"db:{self._label}",
                           (time.perf_counter() - start) * 1000.0, kind="db")
            return timed_execute

        if callable(attr):
            label = self._label

            def chained(*args, **kwargs):
                result = attr(*args, **kwargs)
                # Re-wrap if the result is still a chainable builder
                if hasattr(result, "execute"):
                    return _TimedQueryBuilder(result, label)
                return result
            return chained

        return attr


class _TimedSupabase:
    """Wraps a Supabase Client. Only ``.table()`` and ``.rpc()`` are instrumented;
    storage / auth pass through untouched.
    """

    __slots__ = ("_c",)

    def __init__(self, client: Client) -> None:
        self._c = client

    def table(self, name: str):
        return _TimedQueryBuilder(self._c.table(name), label=f"table:{name}")

    def rpc(self, fn: str, params: dict | None = None):
        return _TimedQueryBuilder(
            self._c.rpc(fn, params or {}), label=f"rpc:{fn}",
        )

    def __getattr__(self, name: str):
        # storage, auth, postgrest, functions — passthrough
        return getattr(self._c, name)


# ── Supabase client (singleton per Streamlit runtime) ─────────────────────

@st.cache_resource(ttl=300)  # 5분마다 재연결 — 유휴 연결 끊김 방지
def _raw_supabase() -> Client:
    """Cached real Supabase client. TTL=300s so idle connections don't expire."""
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)


def get_supabase():
    """Return Supabase client wrapped with timing proxy."""
    return _TimedSupabase(_raw_supabase())


def db_backend() -> str:
    """Backend toggle. 'supabase' (default) | 'sqlite'."""
    return str(st.secrets.get("DB_BACKEND", "supabase")).lower()


def con_open():
    """Compatibility shim — returns a Supabase Client (preferred) or sqlite Connection.

    All call sites have been migrated to expect a Supabase ``Client``; the sqlite
    branch is kept only as a manual fallback for offline diagnostics.
    """
    if db_backend() == "sqlite":
        import sqlite3
        ensure_dir(get_base_dir())
        con = sqlite3.connect(str(path_db()), check_same_thread=False)
        con.row_factory = sqlite3.Row
        return con
    return get_supabase()


# ── Local file paths (PDF/photo cache, fonts, signatures) ────────────────

def get_base_dir() -> Path:
    return Path(st.session_state.get("BASE_DIR", "MaterialToolShared"))


def path_db() -> Path:
    """Legacy SQLite path (only used when DB_BACKEND='sqlite')."""
    return get_base_dir() / "gate_tool.db"


def path_output_root() -> Path:
    return get_base_dir() / "output"


def path_output() -> dict:
    """Local output directories (used as a tmp cache for PDF/QR generation)."""
    root = path_output_root()
    return {
        "plan":   ensure_dir(root / "plan"),
        "permit": ensure_dir(root / "permit"),
        "check":  ensure_dir(root / "check"),
        "exec":   ensure_dir(root / "exec"),
        "photo":  ensure_dir(root / "photo"),
        "qr":     ensure_dir(root / "qr"),
        "bundle": ensure_dir(root / "bundle"),
        "zip":    ensure_dir(root / "zip"),
        "sign":   ensure_dir(root / "sign"),
        "stamp":  ensure_dir(root / "stamp"),
    }


# ── Storage helpers ───────────────────────────────────────────────────────

def photos_bucket() -> str:
    return str(st.secrets.get("SUPABASE_PHOTOS_BUCKET", "photos"))


def outputs_bucket() -> str:
    return str(st.secrets.get("SUPABASE_OUTPUTS_BUCKET", "material-gate"))
