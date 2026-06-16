"""자재 저장(지하 터미널) 배정 + 점유 현황 헬퍼.

- 하역(지상 A~G존) / 저장(지하 터미널 B1·B2-01~13)은 별개 위치.
- 저장은 여러 날 점유(기본 14일, 관리자 수정 가능). 터미널 = 1자재 배타적.
- requests.store_terminal / store_start / store_end / store_released 사용.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from supabase import Client

from db.models import settings_get


# 점유로 치는 요청 상태 (대기·승인·실행·완료/보관중). 반려 제외.
STORAGE_BLOCKING_STATUS = {"PENDING_APPROVAL", "APPROVED", "EXECUTING", "DONE"}
_TERMINAL_RE = re.compile(r"^B[12]-\d{2}$")


def floor_image(name: str) -> Optional[str]:
    """도면 이미지 경로. name: 'b1' | 'b2' | 'ground'. 없으면 None."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    p = os.path.join(root, "assets", f"floor_{name}.jpg")
    return p if os.path.exists(p) else None


# ── 하역 시간 슬롯 (지상, 06:00~18:00 30분) ───────────────────────────

# 하역 슬롯 점유로 치는 상태 (당일 일정 기준 — DONE 제외)
HAEYEOK_BLOCKING = {"PENDING_APPROVAL", "APPROVED", "EXECUTING"}


def haeyeok_slots() -> List[str]:
    out, t = [], 6 * 60
    while t < 18 * 60:
        out.append(f"{t // 60:02d}:{t % 60:02d}")
        t += 30
    return out


def slot_end(s: str) -> str:
    h, m = (int(x) for x in s.split(":"))
    t = h * 60 + m + 30
    return f"{t // 60:02d}:{t % 60:02d}"


def _zone_short(z: Optional[str]) -> str:
    z = (z or "").strip()
    return z.replace("-Zone", "").replace("Zone", "").replace("존", "").strip() or z


def haeyeok_booked_slots(con: Client, project_id: str, date: str, zone: str,
                         kind: str, exclude_rid: Optional[str] = None) -> Dict[str, Dict[str, str]]:
    """같은 날짜·하역존·구분의 다른 신청이 점유한 30분 슬롯 → 점유 상세.

    반환: {slot: {"company","item","requester","role","username","range"}}
    (먼저 잡은 신청 기준. range = 그 신청의 점유 시간대 "HH:MM~HH:MM")
    """
    if not date:
        return {}
    res = (con.table("requests")
           .select("id,time_from,time_to,booking_zone,status,company_name,item_name,"
                   "requester_name,requester_role,requester_username")
           .eq("project_id", project_id)
           .eq("date", date[:10])
           .eq("kind", kind)
           .execute())
    zs = _zone_short(zone)
    all_slots = haeyeok_slots()
    booked: Dict[str, Dict[str, str]] = {}
    for r in res.data or []:
        if exclude_rid and r["id"] == exclude_rid:
            continue
        if r.get("status") not in HAEYEOK_BLOCKING:
            continue
        if _zone_short(r.get("booking_zone")) != zs:
            continue
        tf = (r.get("time_from") or "")[:5]
        tt = (r.get("time_to") or "")[:5]
        if not tf or not tt:
            continue
        info = {
            "company":  r.get("company_name") or "",
            "item":     r.get("item_name") or "",
            "requester": r.get("requester_name") or "",
            "role":     r.get("requester_role") or "",
            "username": r.get("requester_username") or "",
            "range":    f"{tf}~{tt}",
        }
        for s in all_slots:
            if tf <= s < tt:
                booked.setdefault(s, info)
    return booked


# ── 위치 상수 ─────────────────────────────────────────────────────────

def terminals_b1() -> List[str]:
    return [f"B1-{i:02d}" for i in range(1, 14)]


def terminals_b2() -> List[str]:
    return [f"B2-{i:02d}" for i in range(1, 14)]


def all_terminals() -> List[str]:
    return terminals_b1() + terminals_b2()


def ground_zones(con: Client) -> List[str]:
    """하역 지상 존 (A~G). booking_zones_json 재사용."""
    try:
        zs = json.loads(settings_get(con, "booking_zones_json", '["A-Zone"]'))
        return [z for z in zs if z] or ["A-Zone"]
    except Exception:
        return ["A-Zone"]


def default_days(con: Client) -> int:
    """기본 저장 기간(일). 관리자 설정."""
    try:
        return max(1, int(settings_get(con, "storage_default_days", "14")))
    except Exception:
        return 14


# ── 날짜 유틸 ─────────────────────────────────────────────────────────

def add_days(date_str: str, days: int) -> str:
    try:
        d = datetime.strptime(date_str[:10], "%Y-%m-%d")
        return (d + timedelta(days=days)).strftime("%Y-%m-%d")
    except Exception:
        return date_str


def _overlaps(s1: str, e1: str, s2: str, e2: str) -> bool:
    """[s1,e1] 와 [s2,e2] (YYYY-MM-DD, 포함) 겹침 여부."""
    return s1 <= e2 and s2 <= e1


# ── 점유 현황 / 충돌 ──────────────────────────────────────────────────

def _eff_terminal(r: Dict[str, Any]) -> Optional[str]:
    """유효 터미널: store_terminal 우선, 없으면 gate(터미널 형식일 때만)."""
    t = (r.get("store_terminal") or "").strip()
    if _TERMINAL_RE.match(t):
        return t
    g = (r.get("gate") or "").split("|")[0].strip()
    if _TERMINAL_RE.match(g):
        return g
    return None


def _eff_period(r: Dict[str, Any], ddays: int) -> Optional[tuple]:
    """유효 점유 기간: store_start~store_end 있으면 그것, 없으면 반입일~+기본일."""
    s = (r.get("store_start") or "")[:10]
    e = (r.get("store_end") or "")[:10]
    if s and e:
        return s, e
    d = (r.get("date") or r.get("created_at") or "")[:10]
    if len(d) < 10:
        return None
    return d, add_days(d, ddays)


def _storage_rows(con: Client, project_id: str) -> List[Dict[str, Any]]:
    """점유로 칠 반입(IN) 요청 — gate 기준 유효터미널 + 다중일 기간."""
    ddays = default_days(con)
    res = (con.table("requests")
           .select("id,item_name,company_name,kind,status,gate,date,created_at,"
                   "store_terminal,store_start,store_end,store_released")
           .eq("project_id", project_id)
           .eq("kind", "IN")
           .execute())
    out = []
    for r in res.data or []:
        if r.get("store_released"):
            continue
        if r.get("status") not in STORAGE_BLOCKING_STATUS:
            continue
        term = _eff_terminal(r)
        if not term:
            continue
        per = _eff_period(r, ddays)
        if not per:
            continue
        out.append({**r, "_term": term, "_start": per[0], "_end": per[1]})
    return out


def occupancy_on(con: Client, project_id: str, on_date: str) -> Dict[str, Dict[str, Any]]:
    """특정 날짜에 점유 중인 터미널 → 점유 정보. {terminal: {...}} (배타적: 먼저 잡은 것)"""
    d = on_date[:10]
    out: Dict[str, Dict[str, Any]] = {}
    for r in _storage_rows(con, project_id):
        if r["_start"] <= d <= r["_end"]:
            out.setdefault(r["_term"], {
                "rid": r["id"], "item": r.get("item_name") or "",
                "company": r.get("company_name") or "",
                "start": r["_start"], "end": r["_end"],
            })
    return out


def conflicts(con: Client, project_id: str, terminal: str,
              start: str, end: str, exclude_rid: Optional[str] = None) -> List[Dict[str, Any]]:
    """선택 터미널이 [start,end] 기간에 다른 점유와 겹치는지."""
    out = []
    for r in _storage_rows(con, project_id):
        if r["_term"] != terminal:
            continue
        if exclude_rid and r["id"] == exclude_rid:
            continue
        if _overlaps(start[:10], end[:10], r["_start"], r["_end"]):
            out.append(r)
    return out


# ── 배정 저장 ─────────────────────────────────────────────────────────

def assign_storage(con: Client, rid: str, *, store_terminal: Optional[str],
                   store_start: str, store_end: str,
                   booking_zone: Optional[str] = None,
                   time_from: Optional[str] = None,
                   time_to: Optional[str] = None,
                   sync_gate: bool = True) -> None:
    """요청에 하역존/시간 + 저장 터미널/기간 반영.

    sync_gate=True 면 선택 터미널을 gate 필드에도 반영(기존 신청-페이지
    터미널 시스템과 일치). 터미널 미지정 시 gate 는 건드리지 않음.
    """
    patch: Dict[str, Any] = {
        "store_terminal": store_terminal or None,
        "store_start":    store_start,
        "store_end":      store_end,
        "store_released": 0,
    }
    if booking_zone is not None:
        patch["booking_zone"] = booking_zone
    if time_from is not None:
        patch["time_from"] = time_from
    if time_to is not None:
        patch["time_to"] = time_to
    if sync_gate and store_terminal:
        patch["gate"] = store_terminal
    con.table("requests").update(patch).eq("id", rid).execute()


def release_storage(con: Client, rid: str) -> None:
    con.table("requests").update({"store_released": 1}).eq("id", rid).execute()
