"""터미널 보관·반출 CRUD."""
from __future__ import annotations

import re
from datetime import date as _date
from typing import Dict, List, Optional

from supabase import Client

from db.models import settings_get
from shared.helpers import now_str

_TERMINAL_RE = re.compile(r"^B[12]-\d{2}$")
_BLOCKED = {"PENDING_APPROVAL", "APPROVED", "EXECUTING", "DONE"}

_SEL = ("id,company_name,item_name,status,kind,date,"
        "store_terminal,gate,store_released,store_released_at,store_released_by")


def _eff_terminal(r: Dict) -> Optional[str]:
    t = (r.get("store_terminal") or "").strip()
    if _TERMINAL_RE.match(t):
        return t
    g = (r.get("gate") or "").split("|")[0].strip()
    if _TERMINAL_RE.match(g):
        return g
    return None


def terminal_max_days(con: Client, project_id: str) -> int:
    try:
        return max(1, int(settings_get(con, "storage_default_days", "14")))
    except Exception:
        return 14


def terminal_occupied(con: Client, project_id: str,
                      company: Optional[str] = None) -> List[Dict]:
    """반입일 <= 오늘, 반출 미등록인 터미널 목록."""
    today = _date.today().isoformat()
    res = (con.table("requests")
           .select(_SEL)
           .eq("project_id", project_id)
           .eq("kind", "IN")
           .lte("date", today)
           .execute())
    rows = []
    for r in res.data or []:
        if r.get("store_released"):
            continue
        if r.get("status") not in _BLOCKED:
            continue
        term = _eff_terminal(r)
        if not term:
            continue
        if company and r.get("company_name") != company:
            continue
        rows.append({**r, "terminal": term})
    return sorted(rows, key=lambda x: (x["terminal"], x.get("date", "")))


def terminal_history(con: Client, project_id: str,
                     company: Optional[str] = None) -> List[Dict]:
    """반출 완료 이력."""
    q = (con.table("requests")
         .select(_SEL)
         .eq("project_id", project_id)
         .eq("kind", "IN")
         .eq("store_released", 1))
    if company:
        q = q.eq("company_name", company)
    res = q.order("store_released_at", desc=True).limit(200).execute()
    out = []
    for r in res.data or []:
        term = _eff_terminal(r)
        if not term:
            continue
        out.append({**r, "terminal": term})
    return out


def terminal_release(con: Client, rid: str, released_by: str) -> None:
    """반출 등록 — 점유 해제 + 등록일시·등록자 저장."""
    con.table("requests").update({
        "store_released":    1,
        "store_released_at": now_str(),
        "store_released_by": released_by,
    }).eq("id", rid).execute()
