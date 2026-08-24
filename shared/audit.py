"""예약 시간 변경 이력 기록.

access_logs 는 페이지 이동만 남기므로, 슬롯 시간이 언제 누구에 의해
바뀌었는지 추적할 수 없다. schedule_audit 테이블에 변경 전/후 값을
남겨 겹침 발생 경위를 사후에 복원할 수 있게 한다.

기록 실패가 본 작업을 막아서는 안 되므로 모든 예외를 삼킨다.
"""
import json
from typing import Any, Dict, List, Optional

from shared.helpers import now_str, new_id

# action 값
MOVE        = "move"          # 슬롯 그룹 시간 이동
EDIT        = "edit"          # 예약 내용 수정 (시간 포함 가능)
ADD_SLOT    = "add_slot"      # 슬롯 연장
DELETE_SLOT = "delete_slot"   # 슬롯 1개 삭제
DELETE      = "delete"        # 예약 전체 삭제
CREATE      = "create"        # 신규 예약


def log_change(con, *, project_id: str, req_id: str, action: str,
               before_from: str = "", before_to: str = "",
               after_from: str = "", after_to: str = "",
               detail: Optional[Dict[str, Any]] = None) -> None:
    """변경 이력 1건 기록. 실패해도 조용히 무시."""
    try:
        import streamlit as st
        con.table("schedule_audit").insert({
            "id":              new_id(),
            "project_id":      project_id or "",
            "req_id":          req_id or "",
            "action":          action,
            "before_from":     before_from or "",
            "before_to":       before_to or "",
            "after_from":      after_from or "",
            "after_to":        after_to or "",
            "detail":          json.dumps(detail or {}, ensure_ascii=False),
            "changed_by":      st.session_state.get("USER_ID", ""),
            "changed_by_name": st.session_state.get("USER_NAME", ""),
            "changed_by_role": st.session_state.get("USER_ROLE", ""),
            "created_at":      now_str(),
        }).execute()
    except Exception:
        pass


def slot_range(rows: List[Dict[str, Any]]) -> tuple:
    """슬롯 행 목록의 실제 시간 범위 (최소 time_from, 최대 time_to)."""
    tf = sorted(r.get("time_from", "") for r in rows if r.get("time_from"))
    tt = sorted(r.get("time_to", "")   for r in rows if r.get("time_to"))
    return (tf[0] if tf else ""), (tt[-1] if tt else "")


def history(con, req_id: str) -> List[Dict[str, Any]]:
    """한 요청의 변경 이력 (오래된 순)."""
    try:
        res = (con.table("schedule_audit").select("*")
               .eq("req_id", req_id).order("created_at").execute())
        return res.data or []
    except Exception:
        return []
