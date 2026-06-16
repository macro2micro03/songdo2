"""Request CRUD operations (Supabase)."""
import uuid
from typing import Any, Dict, List, Optional

import streamlit as st
from shared.timing import measure
from supabase import Client

from shared.helpers import now_str


_REQ_COLS = [
    "id", "created_at", "updated_at", "status", "kind", "project_id",
    "company_name", "item_name", "item_type", "work_type",
    "date", "time_from", "time_to",
    "gate", "vehicle_type", "vehicle_ton", "vehicle_count",
    "driver_name", "driver_phone",
    "worker_supervisor", "worker_guide", "worker_manager",
    "loading_method", "notes",
    "requester_name", "requester_role", "requester_username",
    "risk_level", "sic_training_url",
    "booking_zone",
]


def _compute_day_seq(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Add a `day_seq` field (1-based) to each row, partitioned by (project_id, date),
    ordered by (date, created_at, id) — matches the legacy SQLite display ID rule."""
    sorted_rows = sorted(
        rows,
        key=lambda r: (r.get("date") or "", r.get("created_at") or "", r.get("id") or ""),
    )
    counters: Dict[tuple, int] = {}
    by_id: Dict[str, int] = {}
    for r in sorted_rows:
        key = (r.get("project_id") or "", r.get("date") or "")
        counters[key] = counters.get(key, 0) + 1
        by_id[r["id"]] = counters[key]
    for r in rows:
        r["day_seq"] = by_id.get(r.get("id"), 0)
    return rows


@measure("crud.req_insert")


def req_insert(con: Client, data: Dict[str, Any]) -> str:
    rid = uuid.uuid4().hex
    row = {
        "id": rid,
        "created_at": now_str(),
        "updated_at": now_str(),
        "status": "PENDING_APPROVAL",
        **{k: data.get(k) for k in _REQ_COLS
           if k not in ("id", "created_at", "updated_at", "status")},
    }
    con.table("requests").insert(row).execute()
    return rid


@measure("crud.req_get")


def req_get(con: Client, rid: str) -> Optional[Dict[str, Any]]:
    """Get a single request by ID with day_seq."""
    res = con.table("requests").select("*").eq("id", rid).limit(1).execute()
    if not res.data:
        return None
    target = res.data[0]
    pid = target.get("project_id") or ""
    same_day = (con.table("requests")
                .select("id,project_id,date,created_at")
                .eq("project_id", pid)
                .eq("date", target.get("date") or "")
                .execute())
    _compute_day_seq(same_day.data or [])
    target["day_seq"] = next(
        (r["day_seq"] for r in (same_day.data or []) if r["id"] == rid), 0
    )
    return target


@measure("crud.req_list")


def req_list(con: Client,
             status: Optional[str] = None,
             kind: Optional[str] = None,
             limit: int = 300,
             project_id: Optional[str] = None) -> List[Dict[str, Any]]:
    pid = project_id or st.session_state.get("PROJECT_ID", "")
    q = con.table("requests").select("*")
    if pid:
        q = q.eq("project_id", pid)
    if status:
        q = q.eq("status", status)
    if kind:
        q = q.eq("kind", kind)
    q = q.order("created_at", desc=True).limit(limit)
    rows = q.execute().data or []
    return _compute_day_seq(rows)


def req_update_status(con: Client, rid: str, status: str) -> None:
    con.table("requests").update({
        "status": status, "updated_at": now_str(),
    }).eq("id", rid).execute()


def req_update_time(con: Client, rid: str, time_from: str, time_to: str) -> None:
    con.table("requests").update({
        "time_from": time_from, "time_to": time_to, "updated_at": now_str(),
    }).eq("id", rid).execute()


@measure("crud.req_delete")


def req_delete(con: Client, rid: str) -> None:
    """Delete a request and all associated records (cascade)."""
    for tbl in ("approvals", "executions", "photos", "outputs", "schedules"):
        con.table(tbl).delete().eq("req_id", rid).execute()
    con.table("requests").delete().eq("id", rid).execute()
