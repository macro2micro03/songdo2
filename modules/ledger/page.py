"""Ledger (대장) page."""

import json

import streamlit as st
from shared.timing import measure
from supabase import Client

from config import KIND_IN, REQ_STATUS
from modules.request.crud import req_list, req_delete
from shared.helpers import req_display_id
from db.models import settings_get

_STATUS_BADGE = {
    "PENDING_APPROVAL": "⏳ 확정대기",
    "APPROVED": "✅ 확정완료",
    "REJECTED": "❌ 반려",
    "EXECUTING": "🔨 실행중",
    "DONE": "✔️ 등록완료",
}


@measure("page.ledger")


def page_ledger(con: Client):
    st.markdown("""
    <style>
    [data-testid="stSelectbox"] [data-testid="stWidgetLabel"],
    [data-testid="stSelectbox"] label {
        margin-bottom: -14px !important;
        padding-bottom: 0 !important;
        line-height: 1 !important;
    }
    [data-testid="stTextInput"] [data-testid="stWidgetLabel"],
    [data-testid="stTextInput"] label {
        margin-bottom: -14px !important;
        padding-bottom: 0 !important;
        line-height: 1 !important;
    }
    /* 대장 행 레이아웃 - 홈과 동일 */
    [class*="st-key-ledger_row_"] .stHorizontalBlock {
        flex-wrap: nowrap !important;
        gap: 4px !important;
    }
    [class*="st-key-ledger_row_"] .stHorizontalBlock > div:first-child {
        flex: 1 1 auto !important;
        min-width: 0 !important;
    }
    [class*="st-key-ledger_row_"] .stHorizontalBlock > div:last-child {
        flex: 0 0 72px !important;
        min-width: 72px !important;
        max-width: 72px !important;
    }
    /* 삭제 버튼 스타일 */
    :root [class*="st-key-ledger_del_"] button {
        background-color: #b91c1c !important;
        border-color: #b91c1c !important;
        border-radius: 4px !important;
        white-space: nowrap !important;
        width: 100% !important;
    }
    :root [class*="st-key-ledger_del_"] button:hover {
        background-color: #991b1b !important;
        border-color: #991b1b !important;
    }
    :root [class*="st-key-ledger_del_"] button,
    :root [class*="st-key-ledger_del_"] button p,
    :root [class*="st-key-ledger_del_"] button span,
    :root [class*="st-key-ledger_del_"] button * {
        color: #f8f8f8 !important;
        white-space: nowrap !important;
        font-size: 12px !important;
    }
    </style>
    """, unsafe_allow_html=True)
    st.markdown("### 📚 대장")
    rows = req_list(con, None, None, 100)

    is_admin  = st.session_state.get("IS_ADMIN", False)
    role      = st.session_state.get("USER_ROLE", "")
    user_name = st.session_state.get("USER_NAME", "")

    # 예약존 목록 로드
    try:
        _bz_all = json.loads(settings_get(con, "booking_zones_json", '["A"]'))
        _bz_dis = json.loads(settings_get(con, "booking_zones_disabled_json", "[]"))
        _bz_opts = [z for z in _bz_all if z not in _bz_dis]
    except Exception:
        _bz_opts = []

    f1, f2 = st.columns(2)
    with f1:
        kind = st.selectbox("구분", ["ALL", "IN", "OUT"])
    with f2:
        status = st.selectbox("상태", ["ALL"] + REQ_STATUS)
    fc1, fc2 = st.columns(2)
    with fc1:
        zone_filter = st.selectbox("예약존", ["ALL"] + _bz_opts) if _bz_opts else "ALL"
    with fc2:
        q = st.text_input("검색").strip().lower()
    filtered = []
    for r in rows:
        if kind != "ALL" and r['kind'] != kind:
            continue
        if status != "ALL" and r['status'] != status:
            continue
        if zone_filter != "ALL" and r.get('booking_zone', 'A') != zone_filter:
            continue
        disp_id = req_display_id(r)
        if q and q not in f"{disp_id} {r.get('company_name','')} {r.get('item_name','')}".lower():
            continue
        filtered.append(r)
    filtered.sort(key=lambda r: (r.get('date') or '', r.get('created_at') or ''), reverse=True)
    st.caption(f"총 {len(filtered)}건")
    for r in filtered:
        rid      = r['id']
        disp_id  = req_display_id(r)
        kind_txt = "반입" if r['kind'] == KIND_IN else "반출"
        badge    = _STATUS_BADGE.get(r['status'], r['status'])
        company  = r.get('company_name') or '-'
        item     = r.get('item_name') or '-'
        date     = (r.get('date') or r.get('created_at') or '')[:10]
        zone     = r.get('booking_zone') or 'A'
        # 신청자 — 이름(직책) + 로그인 ID(있을 때). 구버전 행은 ID 없으면 이름만.
        req_name = r.get('requester_name') or '-'
        req_uid  = r.get('requester_username') or ''
        req_disp = f"{req_name} ({req_uid})" if req_uid else req_name
        line     = (
            f"**{disp_id}** · **[{kind_txt}]** [{zone}] {company} · {item} · {date} | {badge}"
            f"  \n<span style=\"color:#64748b;font-size:12px;\">👤 신청자 {req_disp}</span>"
        )

        can_delete = is_admin

        if can_delete:
            with st.container(key=f"ledger_row_{rid}"):
                tc, dc = st.columns([9, 1])
                with tc:
                    st.markdown(line, unsafe_allow_html=True)
                with dc:
                    if st.button("삭제", key=f"ledger_del_{rid}", type="primary"):
                        req_delete(con, rid)
                        st.toast("삭제되었습니다.", icon="🗑️")
                        st.rerun()
        else:
            st.markdown(line, unsafe_allow_html=True)
