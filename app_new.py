"""Material Gate Tool v3.0.0 — Entry Point.

Modular architecture with project-based authentication
and configurable feature modules.
"""
import streamlit as st

# ── Page config (must be first Streamlit call) ──
st.set_page_config(
    page_title="자재 반출입 관리",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="auto",
)

# ── Imports ──
from db.connection import con_open
from db.migrations import db_init_and_migrate
from core.css import inject_css
from core.header import ui_header
from core.nav import render_topnav
from core.sidebar import render_sidebar
from auth.session import session_has_project, session_is_authed
from auth.login import page_project_select, page_login
from modules.request.page import page_request
from modules.approval.page import page_approval
from modules.execution.page import page_execute
from modules.outputs.page import page_outputs
from modules.ledger.page import page_ledger
from modules.admin.page import page_admin
from modules.schedule.page import page_schedule


# ── Page router ──
PAGE_ROUTER = {
    "요청":     page_request,
    "승인":     page_approval,
    "실행":     page_execute,
    "산출물":   page_outputs,
    "대장":     page_ledger,
    "관리자":   page_admin,
    "스케줄링": page_schedule,
}


def page_home(con):
    """Home page — imported here to avoid circular deps."""
    from modules.request.crud import req_list
    from modules.approval.crud import approvals_inbox
    from modules.execution.crud import photos_for_req
    from config import KIND_IN
    from pathlib import Path
    from shared.helpers import today_str

    role = st.session_state.get("USER_ROLE", "")
    inbox = approvals_inbox(con, role, st.session_state.get("IS_ADMIN", False))
    st.markdown(f"""
    <div class="card">
      <h3 style="margin:0 0 4px 0;">🏠 홈</h3>
      <p style="margin:0 0 8px 0; color:var(--text-secondary); font-size:13px;">요청 → 승인(안전/공사) → 실행(촬영) → 산출물 → 공유</p>
      <p style="margin:0; font-size:13px;"><strong>내 승인함:</strong> {len(inbox)}건</p>
    </div>
    """, unsafe_allow_html=True)

    # 신규 신청 버튼
    if st.button("＋ 신규 신청", key="home_new_req", type="primary", use_container_width=False):
        st.session_state["ACTIVE_PAGE"] = "요청"
        st.rerun()

    # 전체 요청 목록 (진행 중인 건 우선)
    all_reqs = req_list(con, limit=100)
    active_reqs = [r for r in all_reqs if r.get("status") not in ("DONE",)]
    active_reqs = sorted(active_reqs, key=lambda r: r.get("created_at", ""), reverse=True)

    STATUS_LABEL = {
        "PENDING_APPROVAL": ("대기중", "status-pending"),
        "APPROVED":         ("승인됨", "status-approved"),
        "REJECTED":         ("반려됨", "status-rejected"),
        "EXECUTING":        ("실행중", "status-executing"),
        "DONE":             ("완료",   "status-done"),
    }
    PAGE_FOR_STATUS = {
        "PENDING_APPROVAL": "승인",
        "APPROVED":         "실행",
        "REJECTED":         "승인",
        "EXECUTING":        "실행",
        "DONE":             "산출물",
    }

    if not active_reqs:
        st.markdown('<div class="card" style="text-align:center;color:var(--text-muted);font-size:13px;">진행 중인 요청이 없습니다.</div>', unsafe_allow_html=True)
        return

    st.markdown("""
    <style>
    .req-list-wrap { max-height:400px; overflow-y:auto; display:flex; flex-direction:column; gap:8px; padding:4px 0; }
    .req-item { display:flex; align-items:center; gap:10px; background:var(--bg-card); border:1px solid var(--border-light); border-radius:var(--radius-lg); padding:8px 12px; font-size:12px; }
    .req-item-thumb { width:44px; height:44px; border-radius:6px; object-fit:cover; flex-shrink:0; background:var(--neutral-200); display:flex; align-items:center; justify-content:center; color:var(--text-muted); font-size:18px; }
    .req-item-info { flex:1; min-width:0; }
    .req-item-title { font-weight:600; color:var(--text-primary); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
    .req-item-sub { color:var(--text-muted); font-size:11px; margin-top:2px; }
    .status-executing { background:linear-gradient(135deg,#dbeafe,#bfdbfe); color:#1e40af; border:1px solid #3b82f6; }
    .status-done { background:var(--neutral-100); color:var(--text-muted); border:1px solid var(--border-light); }
    </style>
    """, unsafe_allow_html=True)

    for r in active_reqs[:20]:
        rid = r["id"]
        kind = "반입" if r.get("kind") == KIND_IN else "반출"
        status = r.get("status", "PENDING_APPROVAL")
        slabel, scls = STATUS_LABEL.get(status, (status, "status-pending"))
        thumb_html = '<div class="req-item-thumb">📷</div>'
        photos = photos_for_req(con, rid)
        if photos:
            fp = Path(photos[0].get("file_path", ""))
            if fp.exists():
                import base64 as _b64
                img_b64 = _b64.b64encode(fp.read_bytes()).decode()
                thumb_html = f'<img class="req-item-thumb" src="data:image/jpeg;base64,{img_b64}" />'
        title = f"{kind} · {r.get('company_name','')} · {r.get('item_name','')}"
        sub = f"{r.get('date','')} {r.get('time_from','')}~{r.get('time_to','')} GATE:{r.get('gate','')} | {r.get('driver_name','')}"
        st.markdown(f"""
        <div class="req-item">
          {thumb_html}
          <div class="req-item-info">
            <div class="req-item-title">{title}</div>
            <div class="req-item-sub">{sub}</div>
          </div>
          <span class="status-badge {scls}">{slabel}</span>
        </div>
        """, unsafe_allow_html=True)
        target_page = PAGE_FOR_STATUS.get(status, "승인")
        if st.button("→ 이동", key=f"home_goto_{rid}", help=f"{slabel} 화면으로 이동"):
            st.session_state["ACTIVE_PAGE"] = target_page
            st.session_state["SELECTED_REQ_ID"] = rid
            st.rerun()


def main():
    """Main application entry point."""
    # ── DB init ──
    con = con_open()
    db_init_and_migrate(con)

    # ── CSS ──
    inject_css()

    # ── Session defaults ──
    if "AUTH_OK" not in st.session_state:
        st.session_state["AUTH_OK"] = False
    if "BASE_DIR" not in st.session_state:
        st.session_state["BASE_DIR"] = "MaterialToolShared"
    if "ACTIVE_PAGE" not in st.session_state:
        st.session_state["ACTIVE_PAGE"] = "홈"

    # ── Step 1: Project selection ──
    if not session_has_project():
        page_project_select(con)
        return

    # ── Step 2: Authentication ──
    if not session_is_authed():
        page_login(con)
        return

    # ── Step 3: Main app ──
    render_sidebar()
    ui_header(con)
    render_topnav(con)

    active_page = st.session_state.get("ACTIVE_PAGE", "홈")
    if active_page == "홈":
        page_home(con)
    elif active_page in PAGE_ROUTER:
        PAGE_ROUTER[active_page](con)
    else:
        st.warning(f"알 수 없는 페이지: {active_page}")


if __name__ == "__main__":
    main()
