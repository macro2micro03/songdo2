"""Module management UI for toggling project modules per role."""

import streamlit as st
from supabase import Client

from db.models import modules_for_project, module_toggle, module_toggle_role


def render_module_manager(con: Client, project_id: str):
    st.markdown("#### 📦 기능 모듈 설정")
    st.markdown("""<style>
    /* ── 토글 셀 컨테이너: flex 중앙 정렬 ── */
    [class*="st-key-mcell_a_"],
    [class*="st-key-mcell_u_"] {
        display: flex !important;
        justify-content: center !important;
        align-items: center !important;
        width: 100% !important;
    }
    [class*="st-key-mcell_a_"] > div,
    [class*="st-key-mcell_u_"] > div,
    [class*="st-key-mcell_a_"] [data-testid="stVerticalBlock"],
    [class*="st-key-mcell_u_"] [data-testid="stVerticalBlock"],
    [class*="st-key-mcell_a_"] [data-testid="stElementContainer"],
    [class*="st-key-mcell_u_"] [data-testid="stElementContainer"] {
        display: flex !important;
        justify-content: center !important;
        align-items: center !important;
        width: 100% !important;
        margin: 0 !important;
        padding: 0 !important;
    }
    [class*="st-key-mcell_a_"] [data-testid="stCheckbox"],
    [class*="st-key-mcell_a_"] [data-testid="stToggle"],
    [class*="st-key-mcell_u_"] [data-testid="stCheckbox"],
    [class*="st-key-mcell_u_"] [data-testid="stToggle"] {
        display: flex !important;
        justify-content: center !important;
    }
    [class*="st-key-mcell_a_"] label,
    [class*="st-key-mcell_u_"] label {
        display: block !important;
        width: fit-content !important;
        margin: 0 auto !important;
    }
    /* 행 구분선 */
    .st-key-mod_mgr_table [data-testid="stHorizontalBlock"] {
        border-bottom: 1px solid #f1f5f9 !important;
        padding: 4px 0 !important;
        align-items: center !important;
        flex-wrap: nowrap !important;
        gap: 8px !important;
    }
    /* ── 모바일: 전역 스택킹 오버라이드 (:has 양성선택자, 특이도 0,4,0 — 전역 0,4,0 동일하나 나중 선언으로 우선) ── */
    @media (max-width: 480px) {
        [data-testid="stHorizontalBlock"]:has([class*="st-key-mcell_a_"]):has([class*="st-key-mcell_u_"]) > [data-testid="stColumn"] {
            flex: 1 1 0 !important;
            min-width: 0 !important;
            max-width: none !important;
        }
        [data-testid="stHorizontalBlock"]:has([class*="st-key-mcell_a_"]):has([class*="st-key-mcell_u_"]) > [data-testid="stColumn"]:first-child {
            flex: 3 1 0 !important;
        }
    }
    /* HTML 헤더 스타일 */
    .mod-mgr-hdr {
        display: flex;
        align-items: center;
        gap: 8px;
        width: 100%;
        box-sizing: border-box;
        padding-bottom: 6px;
        border-bottom: 2px solid #e2e8f0;
        margin-bottom: 4px;
    }
    .mod-mgr-hdr-name {
        flex: 3;
        min-width: 0;
        font-size: 12px;
        font-weight: 600;
        color: #475569;
    }
    .mod-mgr-hdr-admin {
        flex: 1;
        min-width: 0;
        font-size: 11px;
        font-weight: 600;
        color: #1d4ed8;
        text-align: center;
        white-space: nowrap;
    }
    .mod-mgr-hdr-user {
        flex: 1;
        min-width: 0;
        font-size: 11px;
        font-weight: 600;
        color: #059669;
        text-align: center;
        white-space: nowrap;
    }
    </style>""", unsafe_allow_html=True)

    modules = modules_for_project(con, project_id)

    with st.container(key="mod_mgr_table"):
        # 헤더 — 순수 HTML flexbox (Streamlit 컬럼 스택킹 영향 없음)
        st.markdown("""
        <div class="mod-mgr-hdr">
            <div class="mod-mgr-hdr-name" style="text-align:center;">기능명</div>
            <div class="mod-mgr-hdr-admin">관리자</div>
            <div class="mod-mgr-hdr-user">일반사용자</div>
        </div>
        """, unsafe_allow_html=True)

        # 데이터 행
        for mod in modules:
            key      = mod["module_key"]
            name     = mod["module_name"]
            en_admin = bool(mod.get("enabled_admin", mod["enabled"]))
            en_user  = bool(mod.get("enabled_user",  mod["enabled"]))

            r1, r2, r3 = st.columns([3, 1, 1])
            with r1:
                st.markdown(f'<p style="font-size:13px;color:#0f172a;margin:0;padding:2px 0;text-align:center;">{name}</p>', unsafe_allow_html=True)
            with r2:
                with st.container(key=f"mcell_a_{key}"):
                    new_admin = st.toggle("", value=en_admin,
                                          key=f"tog_admin_{key}",
                                          label_visibility="collapsed")
                if new_admin != en_admin:
                    module_toggle_role(con, project_id, key, "admin", int(new_admin))
                    module_toggle(con, project_id, key, int(new_admin or en_user))
                    st.rerun()
            with r3:
                with st.container(key=f"mcell_u_{key}"):
                    new_user = st.toggle("", value=en_user,
                                         key=f"tog_user_{key}",
                                         label_visibility="collapsed")
                if new_user != en_user:
                    module_toggle_role(con, project_id, key, "user", int(new_user))
                    module_toggle(con, project_id, key, int(en_admin or new_user))
                    st.rerun()
