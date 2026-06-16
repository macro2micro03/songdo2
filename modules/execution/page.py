"""Execution registration page."""

import streamlit as st
from shared.timing import measure
from supabase import Client

from datetime import date
from modules.request.crud import req_list, req_update_status
from modules.execution.crud import execution_upsert, execution_get
from shared.helpers import req_display_id
from modules.execution.photos import ui_photo_upload
from modules.outputs.crud import generate_all_outputs


def _do_confirm(con, rid: str, reedit_key: str):
    """Execute confirmation."""
    try:
        req_update_status(con, rid, "EXECUTING")
        execution_upsert(con, rid, st.session_state.get("USER_NAME", ""), st.session_state.get("USER_ROLE", ""), {}, "")
        req_update_status(con, rid, "DONE")
    except Exception as e:
        st.error(f"저장 오류: {e}")
        st.stop()
    try:
        generate_all_outputs(con, rid)
    except Exception:
        pass
    st.session_state.pop(reedit_key, None)
    st.toast("확인 등록 완료!", icon="✅")
    st.rerun()


@measure("page.execute")


def page_execute(con: Client):
    st.markdown("""
    <style>
    [data-testid="stSelectbox"] [data-testid="stWidgetLabel"],
    [data-testid="stSelectbox"] label {
        margin-bottom: -14px !important;
        padding-bottom: 0 !important;
        line-height: 1 !important;
    }
    .st-key-exec_confirm_btn button {
        height: 52px !important;
        min-height: 52px !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        padding: 0 !important;
        font-size: 15px !important;
        font-weight: 700 !important;
    }
    .st-key-exec_confirm_btn button p {
        line-height: 1 !important;
        margin: 0 !important;
        font-size: 15px !important;
        font-weight: 700 !important;
    }
    .st-key-exec_done_btn button {
        background: #6b7280 !important;
        border-color: #6b7280 !important;
        color: #ffffff !important;
        cursor: default !important;
    }
    .st-key-exec_done_btn button p { color: #ffffff !important; }
    .st-key-exec_done_btn button:hover {
        background: #6b7280 !important;
        transform: none !important;
        box-shadow: none !important;
    }
    .st-key-exec_reedit_btn button {
        background: #f59e0b !important;
        border-color: #f59e0b !important;
        color: #ffffff !important;
    }
    .st-key-exec_reedit_btn button p { color: #ffffff !important; }
    .st-key-exec_reedit_btn button:hover {
        background: #d97706 !important;
        border-color: #d97706 !important;
        transform: none !important;
    }
    </style>
    """, unsafe_allow_html=True)

    st.markdown("### 📸 사진 등록")
    today = date.today().isoformat()
    candidates = [
        r for r in req_list(con, None, None, 500)
        if r['status'] in ['APPROVED', 'EXECUTING', 'DONE']
        and (r.get('date') or '') >= today
    ]
    if not candidates:
        st.info("실행 등록 가능한 요청이 없습니다.")
        return

    items = [(f"{req_display_id(r)} · {r['company_name']} · {r['item_name']}", r['id']) for r in candidates]
    sel = st.selectbox("확인 대상", items, format_func=lambda x: x[0])
    rid = sel[1]

    exec_row   = execution_get(con, rid)
    is_done    = exec_row is not None
    reedit_key = f"exec_reedit_{rid}"

    st.markdown("#### 📷 사진 등록 (최대 4장)")
    ui_photo_upload(con, rid)

    st.markdown("<div style='margin-bottom:32px'></div>", unsafe_allow_html=True)

    if is_done and not st.session_state.get(reedit_key, False):
        col_done, col_reedit = st.columns(2)
        with col_done:
            st.button("등록 완료", key="exec_done_btn", use_container_width=True, type="primary")
        with col_reedit:
            if st.button("재등록", key="exec_reedit_btn", use_container_width=True, type="primary"):
                st.session_state[reedit_key] = True
                st.rerun()
    else:
        with st.container(key="exec_confirm_btn"):
            if st.button("확인 등록", key="exec_confirm_bottom", type="primary", use_container_width=True):
                _do_confirm(con, rid, reedit_key)
