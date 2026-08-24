"""Schedule CRUD operations."""
import time
from shared.timing import measure
from typing import List, Dict, Any, Optional

from supabase import Client

from shared.helpers import now_str, new_id

_SYNC_TTL = 60  # schedule_sync_from_requests 최소 실행 간격(초)


@measure("crud.schedule_insert")


def schedule_insert(con: Client, project_id, data: dict) -> str:
    """Insert a new schedule entry. Returns schedule id."""
    sid = new_id()
    con.table("schedules").insert({
        "id": sid,
        "project_id": project_id,
        "req_id": data.get("req_id", ""),
        "title": data["title"],
        "schedule_date": data["schedule_date"],
        "time_from": data["time_from"],
        "time_to": data["time_to"],
        "kind": data.get("kind", "IN"),
        "gate": data.get("gate", ""),
        "company_name": data.get("company_name", ""),
        "vehicle_info": data.get("vehicle_info", ""),
        "status": data.get("status", "PENDING"),
        "color": data.get("color", "#fbbf24"),
        "created_by": data.get("created_by", ""),
        "created_at": now_str(),
        "booking_zone": data.get("booking_zone", "A"),
    }).execute()
    return sid


def schedule_list_by_date(
    con: Client, project_id, schedule_date, booking_zone: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Get all schedules for a date (optionally filtered by booking_zone)."""
    q = (con.table("schedules").select("*")
         .eq("project_id", project_id).eq("schedule_date", schedule_date))
    if booking_zone:
        q = q.eq("booking_zone", booking_zone)
    res = q.order("time_from").execute()
    return res.data or []


def schedule_update(con: Client, sid, **kwargs):
    """Update a schedule entry by id. Pass column=value pairs as kwargs."""
    if not kwargs:
        return
    allowed = {
        "title", "schedule_date", "time_from", "time_to", "kind", "gate",
        "company_name", "vehicle_info", "status", "color", "req_id", "booking_zone",
    }
    filtered = {k: v for k, v in kwargs.items() if k in allowed}
    if not filtered:
        return
    con.table("schedules").update(filtered).eq("id", sid).execute()


def schedule_delete(con: Client, sid):
    """Delete a schedule entry by id."""
    con.table("schedules").delete().eq("id", sid).execute()


@measure("crud.schedule_get")


def schedule_get(con: Client, sid) -> Optional[Dict[str, Any]]:
    """Get a single schedule entry by id."""
    res = con.table("schedules").select("*").eq("id", sid).limit(1).execute()
    return res.data[0] if res.data else None


@measure("crud.schedule_by_req_id")


def schedule_by_req_id(con: Client, req_id: str) -> Optional[Dict[str, Any]]:
    """Get the first schedule entry linked to a request id."""
    res = (con.table("schedules").select("*").eq("req_id", req_id)
           .order("created_at").limit(1).execute())
    return res.data[0] if res.data else None


def schedule_sync_from_requests(con: Client, project_id):
    """Sync schedule entries from existing approved requests (auto-populate).

    For each approved request that does not yet have a corresponding schedule
    entry, create one automatically. 60초 이내 재호출은 스킵.
    """
    import streamlit as st
    _tk = f"_sched_sync_ts_{project_id}"
    _now = time.monotonic()
    if _now - st.session_state.get(_tk, 0) < _SYNC_TTL:
        return
    # TTL을 먼저 설정 — 이후 작업이 느려도 다음 렌더가 중복 실행하지 않도록
    st.session_state[_tk] = _now

    try:
        req_res = (con.table("requests").select("*")
                   .eq("project_id", project_id)
                   .in_("status", ["PENDING_APPROVAL", "APPROVED"])
                   .execute())
    except Exception:
        return
    requests = req_res.data or []
    if not requests:
        return

    # 기존 schedules 의 req_id 전체 수집.
    # ⚠️ PostgREST 는 기본 1000행만 반환하므로 반드시 페이지네이션.
    #    (누락되면 이미 동기화된 요청을 계속 재삽입해 중복이 무한 증가함)
    existing_req_ids = set()
    _page, _size = 0, 1000
    try:
        while True:
            _res = (con.table("schedules").select("req_id")
                    .eq("project_id", project_id)
                    .range(_page * _size, _page * _size + _size - 1)
                    .execute())
            _rows = _res.data or []
            existing_req_ids.update(s["req_id"] for s in _rows if s.get("req_id"))
            if len(_rows) < _size:
                break
            _page += 1
    except Exception:
        # 조회 실패 시 중복 삽입 위험이 있으므로 아예 동기화하지 않음
        return

    from config import TIME_SLOTS
    from shared.helpers import new_id, now_str
    bulk_rows = []
    _seen = set()   # (req_id, time_from, time_to) — 배치 내 중복 방지
    for r in requests:
        if r["id"] in existing_req_ids:
            continue
        req_status   = r.get("status", "")
        sched_status = "PENDING" if req_status == "PENDING_APPROVAL" else "APPROVED"
        sched_color  = "#fbbf24" if sched_status == "PENDING" else "#22c55e"
        time_from    = r.get("time_from", "08:00") or "08:00"
        time_to      = r.get("time_to") or _add_30min(time_from)
        try:
            fi = TIME_SLOTS.index(time_from)
            ti = TIME_SLOTS.index(time_to)
        except ValueError:
            fi, ti = 0, 1
        slot_pairs = [(TIME_SLOTS[i], TIME_SLOTS[i + 1])
                      for i in range(fi, ti) if i + 1 < len(TIME_SLOTS)]
        if not slot_pairs:
            slot_pairs = [(time_from, _add_30min(time_from))]
        base = {
            "project_id":    project_id,
            "req_id":        r.get("id", ""),
            "title":         r.get("company_name", "자재 반출입"),
            "schedule_date": r.get("date", r.get("created_at", "")[:10]),
            "kind":          r.get("kind", "IN"),
            "gate":          r.get("gate", ""),
            "company_name":  r.get("company_name", ""),
            "vehicle_info":  f"{r.get('vehicle_type','')} {r.get('vehicle_ton','')}t".strip(),
            "status":        sched_status,
            "color":         sched_color,
            "created_by":    "system",
            "booking_zone":  r.get("booking_zone", "A"),
            "created_at":    now_str(),
        }
        for sf, st_ in slot_pairs:
            _k = (base["req_id"], sf, st_)
            if _k in _seen:
                continue
            _seen.add(_k)
            bulk_rows.append({**base, "id": new_id(), "time_from": sf, "time_to": st_})

    if not bulk_rows:
        return
    # 100행씩 bulk insert. schedules_req_slot_uniq 인덱스와 충돌하면
    # 배치 전체가 실패하므로, 실패 시 행 단위로 재시도해 충돌 행만 건너뜀.
    for i in range(0, len(bulk_rows), 100):
        chunk = bulk_rows[i:i + 100]
        try:
            con.table("schedules").insert(chunk).execute()
        except Exception:
            for row in chunk:
                try:
                    con.table("schedules").insert(row).execute()
                except Exception:
                    pass


def _add_30min(time_str: str) -> str:
    """Add 30 minutes to a HH:MM time string."""
    try:
        parts = time_str.split(":")
        h, m = int(parts[0]), int(parts[1])
        m += 30
        if m >= 60:
            m -= 60
            h += 1
        if h >= 24:
            h = 23
            m = 59
        return f"{h:02d}:{m:02d}"
    except (ValueError, IndexError):
        return "08:30"
