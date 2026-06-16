"""Approval CRUD operations."""

from shared.timing import measure
import json
import uuid
from typing import Dict, Any, List, Optional, Tuple

from supabase import Client

from shared.helpers import now_str
from db.models import settings_get
from modules.request.crud import req_update_status


def routing_get(con: Client) -> Dict[str, List[str]]:
    """Get the approval routing configuration."""
    try:
        return json.loads(settings_get(con, "approval_routing_json", "{}"))
    except Exception:
        return {"IN": ["공사"], "OUT": ["안전", "공사"]}


def approvals_create_default(con: Client, rid: str, kind: str) -> None:
    """Create default approval steps for a request based on its kind."""
    roles = routing_get(con).get(kind, ["공사"]) or ["공사"]
    rows = [
        {"id": uuid.uuid4().hex, "req_id": rid, "step_no": i,
         "role_required": role, "status": "PENDING", "created_at": now_str()}
        for i, role in enumerate(roles, start=1)
    ]
    if rows:
        con.table("approvals").insert(rows).execute()


@measure("crud.approvals_inbox")


def approvals_inbox(
    con: Client, user_role: str, is_admin: bool,
    project_id: str = "",
) -> List[Dict[str, Any]]:
    """Get pending approvals for the current user's inbox."""
    import streamlit as st
    pid = project_id or st.session_state.get("PROJECT_ID", "")
    try:
        res = con.rpc("rpc_approvals_inbox", {
            "p_project_id": pid,
            "p_user_role": user_role,
            "p_is_admin": is_admin,
        }).execute()
        return res.data or []
    except Exception:
        # fallback — manual two-step fetch
        ap = (con.table("approvals")
              .select("*, requests!inner(kind, company_name, item_name, date, time_from, time_to, gate, status, created_at, project_id)")
              .eq("status", "PENDING")
              .eq("requests.project_id", pid)
              .execute())
        rows = ap.data or []
        # filter to first PENDING step per req
        by_req: Dict[str, List[Dict[str, Any]]] = {}
        for r in rows:
            by_req.setdefault(r["req_id"], []).append(r)
        out: List[Dict[str, Any]] = []
        for rid, items in by_req.items():
            min_step = min(it["step_no"] for it in items)
            for it in items:
                if it["step_no"] != min_step:
                    continue
                if not is_admin and it.get("role_required") != user_role:
                    continue
                nested = it.pop("requests", {}) or {}
                it.update({k: nested.get(k) for k in
                          ("kind", "company_name", "item_name", "date",
                           "time_from", "time_to", "gate")})
                it["req_status"] = nested.get("status")
                it["_created_at"] = nested.get("created_at", "")
                out.append(it)
        out.sort(key=lambda r: (r.pop("_created_at", "") or "", r.get("step_no", 0)),
                 reverse=True)
        return out


@measure("crud.approvals_for_req")


def approvals_for_req(con: Client, rid: str) -> List[Dict[str, Any]]:
    """Get all approval steps for a given request."""
    res = (con.table("approvals").select("*").eq("req_id", rid)
           .order("step_no").execute())
    return res.data or []


@measure("crud.approval_mark")


def approval_mark(
    con: Client,
    approval_id: str,
    action: str,
    signer_name: str,
    signer_role: str,
    sign_path: Optional[str],
    stamp_path: Optional[str],
    reject_reason: str = "",
) -> Tuple[str, str]:
    """Mark an approval as APPROVED or REJECTED."""
    try:
        res = con.rpc("rpc_approval_mark", {
            "p_approval_id": approval_id,
            "p_action": action,
            "p_signer_name": signer_name,
            "p_signer_role": signer_role,
            "p_sign_path": sign_path,
            "p_stamp_path": stamp_path,
            "p_reject_reason": reject_reason,
        }).execute()
        data = res.data or {}
        if isinstance(data, list):
            data = data[0] if data else {}
        return data.get("rid", ""), data.get("msg", "")
    except Exception:
        # fallback — manual update
        cur_res = (con.table("approvals").select("req_id,status")
                   .eq("id", approval_id).limit(1).execute())
        if not cur_res.data:
            return "", "승인항목을 찾지 못했습니다."
        row = cur_res.data[0]
        rid = row["req_id"]
        if row["status"] != "PENDING":
            return rid, "이미 처리된 승인입니다."
        if action == "APPROVE":
            con.table("approvals").update({
                "status": "APPROVED",
                "signer_name": signer_name,
                "signer_role": signer_role,
                "sign_png_path": sign_path,
                "stamp_png_path": stamp_path,
                "signed_at": now_str(),
            }).eq("id", approval_id).execute()
            left_res = (con.table("approvals").select("id", count="exact")
                        .eq("req_id", rid).eq("status", "PENDING").execute())
            left = left_res.count or 0
            if left == 0:
                req_update_status(con, rid, "APPROVED")
                return rid, "최종 승인 완료"
            return rid, "승인 완료(다음 승인자 대기)"
        con.table("approvals").update({
            "status": "REJECTED",
            "signer_name": signer_name,
            "signer_role": signer_role,
            "reject_reason": reject_reason,
            "signed_at": now_str(),
        }).eq("id", approval_id).execute()
        req_update_status(con, rid, "REJECTED")
        return rid, "반려 처리 완료"
