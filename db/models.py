"""CRUD for projects, project_modules, settings (Supabase)."""
from shared.timing import measure
import uuid
from typing import Any, Dict, List, Optional

from supabase import Client

from shared.helpers import now_str


# ── Settings ──────────────────────────────────────────────────────────

import streamlit as st

def _settings_load(sb: Client) -> Dict[str, str]:
    """DB에서 settings 전체를 한 번에 가져와 dict로 반환."""
    res = sb.table("settings").select("key,value").execute()
    return {r["key"]: r["value"] for r in (res.data or [])}

def settings_get_all(sb: Client) -> Dict[str, str]:
    """rerun 당 1회 DB 조회 후 session_state에 캐시."""
    if "_settings_cache" not in st.session_state:
        st.session_state["_settings_cache"] = _settings_load(sb)
    return st.session_state["_settings_cache"]

def settings_invalidate() -> None:
    """settings_set 후 캐시 무효화."""
    st.session_state.pop("_settings_cache", None)

@measure("models.settings_get")
def settings_get(sb: Client, key: str, default: str = "") -> str:
    return settings_get_all(sb).get(key, default)

def settings_set(sb: Client, key: str, value: str) -> None:
    sb.table("settings").upsert(
        {"key": key, "value": value, "updated_at": now_str()},
        on_conflict="key",
    ).execute()
    settings_invalidate()


# ── Projects ──────────────────────────────────────────────────────────

def project_create(sb: Client, name: str, description: str,
                   site_pin: str, admin_pin: str) -> str:
    pid = uuid.uuid4().hex
    sb.table("projects").insert({
        "id": pid, "name": name, "description": description,
        "site_pin": site_pin, "admin_pin": admin_pin, "created_at": now_str(),
    }).execute()
    modules_init_for_project(sb, pid)
    return pid


@measure("models.project_list")


def project_list(sb: Client) -> List[Dict[str, Any]]:
    res = sb.table("projects").select("*").order("created_at", desc=True).execute()
    return res.data or []


@measure("models.project_get")


def project_get(sb: Client, project_id: str) -> Optional[Dict[str, Any]]:
    res = sb.table("projects").select("*").eq("id", project_id).limit(1).execute()
    return res.data[0] if res.data else None


def project_update(sb: Client, project_id: str, **kwargs) -> None:
    allowed = {"name", "description", "site_pin", "admin_pin"}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return
    sb.table("projects").update(fields).eq("id", project_id).execute()


# ── Project Modules ───────────────────────────────────────────────────

DEFAULT_MODULES = [
    ("schedule",  "📅 신청",     "일정 캘린더 + 신규 요청 등록 통합",          1, 0),
    ("approval",  "✍️ 승인",      "안전/공사 담당자의 요청 승인·반려 처리",      1, 1),
    ("terminal",  "📦 터미널",   "터미널 보관·반출 관리",                       1, 2),
    ("execution", "📸 사진등록",  "현장 사진 촬영 및 등록",                     1, 3),
    ("outputs",   "📄 계획서",    "PDF 계획서·허가서·실행요약 생성 및 공유",     1, 4),
    ("ledger",    "📋 대장",      "전체 요청·승인 내역 검색 및 엑셀 다운로드",   1, 5),
    ("dashboard", "📊 대시보드",  "날짜별 반출입 현황 요약",                    1, 6),
]


def modules_init_for_project(sb: Client, project_id: str) -> None:
    rows = [
        {"project_id": project_id, "module_key": key, "module_name": name,
         "module_desc": desc, "enabled": enabled, "sort_order": order,
         "enabled_admin": 1, "enabled_user": 1}
        for key, name, desc, enabled, order in DEFAULT_MODULES
    ]
    sb.table("project_modules").upsert(rows, on_conflict="project_id,module_key").execute()


def modules_ensure_defaults(sb: Client, project_id: str) -> None:
    """신규 추가된 DEFAULT_MODULES를 기존 프로젝트에 누락 없이 추가."""
    existing = {m["module_key"] for m in modules_for_project(sb, project_id)}
    new_rows = [
        {"project_id": project_id, "module_key": key, "module_name": name,
         "module_desc": desc, "enabled": enabled, "sort_order": order,
         "enabled_admin": 1, "enabled_user": 1}
        for key, name, desc, enabled, order in DEFAULT_MODULES
        if key not in existing
    ]
    if new_rows:
        sb.table("project_modules").upsert(new_rows, on_conflict="project_id,module_key").execute()


@measure("models.modules_for_project")


def modules_for_project(sb: Client, project_id: str) -> List[Dict[str, Any]]:
    res = (sb.table("project_modules").select("*")
           .eq("project_id", project_id).order("sort_order").execute())
    return res.data or []


def modules_enabled_for_project(sb: Client, project_id: str,
                                is_admin: bool = False) -> List[Dict[str, Any]]:
    col = "enabled_admin" if is_admin else "enabled_user"
    res = (sb.table("project_modules").select("*")
           .eq("project_id", project_id).eq("enabled", 1).eq(col, 1)
           .order("sort_order").execute())
    return res.data or []


def module_toggle(sb: Client, project_id: str, module_key: str, enabled: int) -> None:
    (sb.table("project_modules").update({"enabled": enabled})
     .eq("project_id", project_id).eq("module_key", module_key).execute())


def module_toggle_role(sb: Client, project_id: str, module_key: str,
                       role: str, enabled: int) -> None:
    col = "enabled_admin" if role == "admin" else "enabled_user"
    (sb.table("project_modules").update({col: enabled})
     .eq("project_id", project_id).eq("module_key", module_key).execute())
