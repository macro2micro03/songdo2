"""Sidebar rendering."""
import streamlit as st
from shared.timing import measure
from auth.session import auth_reset


@measure("core.render_sidebar")


def render_sidebar():
    """Render sidebar with user info and navigation."""
    with st.sidebar:
        if st.session_state.get("AUTH_OK", False):
            uname = st.session_state.get("USER_NAME", "")
            urole = st.session_state.get("USER_ROLE", "")
            st.markdown(f"""
            <div class="sidebar-user">
              <div class="sidebar-user-name">👤 {uname}</div>
              <div class="sidebar-user-role">{urole}</div>
            </div>
            """, unsafe_allow_html=True)
            st.markdown("---")

            active = st.session_state.get("ACTIVE_PAGE", "홈")
            PAGES = [
                ("홈",        "🏠"),
                ("관리자",    "⚙️"),
            ]
            _LABELS = {
                "홈":     "🏠 홈",
                "관리자": "⚙️ 관리자 설정",
                "내정보": "👤 내 정보 수정",
            }
            for page_name, icon in PAGES:
                btn_type = "primary" if active == page_name else "secondary"
                key = f"nav_{page_name}"
                if page_name == "관리자":
                    with st.container(key="sidebar_admin_btn"):
                        if st.button(_LABELS[page_name], key=key,
                                     use_container_width=True, type=btn_type):
                            st.session_state["ACTIVE_PAGE"] = page_name
                            st.rerun()
                else:
                    if st.button(_LABELS[page_name], key=key,
                                 use_container_width=True, type=btn_type):
                        st.session_state["ACTIVE_PAGE"] = page_name
                        st.rerun()
            # 내 정보 수정 버튼 (모든 사용자)
            with st.container(key="sidebar_profile_btn"):
                profile_type = "primary" if active == "내정보" else "secondary"
                if st.button("👤 내 정보 수정", key="nav_내정보",
                             use_container_width=True, type=profile_type):
                    st.session_state["ACTIVE_PAGE"] = "내정보"
                    st.rerun()
            with st.container(key="sidebar_divider"):
                st.markdown('<hr style="margin:0 !important;padding:0 !important;">', unsafe_allow_html=True)
            if st.button("로그아웃", use_container_width=True):
                auth_reset()
                st.rerun()
        else:
            st.caption("로그인 필요")
