"""터미널 보관·반출 관리 페이지."""
from datetime import date as _date

import streamlit as st
from supabase import Client

from modules.terminal.crud import (
    terminal_max_days, terminal_occupied, terminal_history, terminal_release,
)


def page_terminal(con: Client) -> None:
    role       = st.session_state.get("USER_ROLE", "")
    is_admin   = st.session_state.get("IS_ADMIN", False)
    company    = st.session_state.get("USER_COMPANY", "")
    user_id    = st.session_state.get("USER_ID", "")
    project_id = st.session_state.get("PROJECT_ID", "")

    # 협력사는 본인 업체만 / 관리자·삼성물산은 전체
    filter_co = None if (is_admin or role != "협력사") else company

    max_days = terminal_max_days(con, project_id)

    st.markdown(
        '<div class="card"><h3 style="margin:0 0 4px 0;">📦 터미널 보관·반출 관리</h3>'
        f'<p style="margin:0;font-size:12px;color:var(--text-muted);">최대 보관 기준: {max_days}일</p></div>',
        unsafe_allow_html=True,
    )

    tab1, tab2 = st.tabs(["보관 현황", "반출 이력"])

    # ── 보관 현황 ────────────────────────────────────────────────────────────
    with tab1:
        occupied = terminal_occupied(con, project_id, filter_co)
        if not occupied:
            st.info("현재 보관 중인 자재가 없습니다.")
        else:
            today = _date.today()
            for r in occupied:
                rid    = r["id"]
                term   = r["terminal"]
                co     = r.get("company_name", "")
                item   = r.get("item_name", "")
                d_str  = (r.get("date") or "")[:10]
                try:
                    elapsed = (today - _date.fromisoformat(d_str)).days
                except Exception:
                    elapsed = 0
                over  = elapsed > max_days
                d_clr = "#dc2626" if over else "#1d4ed8"
                warn  = " ⚠️ 기준 초과" if over else ""

                with st.container(key=f"term_occ_{rid}"):
                    c1, c2 = st.columns([8, 2])
                    with c1:
                        st.markdown(
                            f'<div style="padding:6px 0;">'
                            f'<strong style="font-size:14px;">{term}</strong>'
                            f'&nbsp;·&nbsp;{co}&nbsp;·&nbsp;{item}<br>'
                            f'<span style="font-size:12px;color:#64748b;">반입일: {d_str}</span>'
                            f'&nbsp;&nbsp;<span style="font-size:12px;color:{d_clr};'
                            f'font-weight:600;">{elapsed}일 경과{warn}</span></div>',
                            unsafe_allow_html=True,
                        )
                    with c2:
                        if st.button("반출 완료", key=f"rel_{rid}",
                                     type="primary", use_container_width=True):
                            terminal_release(con, rid, user_id)
                            st.toast(f"✅ {term} 반출 등록 완료")
                            st.rerun()

    # ── 반출 이력 ────────────────────────────────────────────────────────────
    with tab2:
        history = terminal_history(con, project_id, filter_co)
        if not history:
            st.info("반출 이력이 없습니다.")
        else:
            for r in history:
                term   = r["terminal"]
                co     = r.get("company_name", "")
                item   = r.get("item_name", "")
                d_str  = (r.get("date") or "")[:10]
                rel_at = (r.get("store_released_at") or "")[:16].replace("T", " ")
                rel_by = r.get("store_released_by") or ""
                by_txt = f" ({rel_by})" if rel_by else ""
                st.markdown(
                    f'<div style="padding:6px 0;border-bottom:1px solid #e2e8f0;">'
                    f'<strong>{term}</strong> · {co} · {item}<br>'
                    f'<span style="font-size:12px;color:#64748b;">'
                    f'반입일: {d_str}&nbsp;|&nbsp;반출: {rel_at}{by_txt}'
                    f'</span></div>',
                    unsafe_allow_html=True,
                )
