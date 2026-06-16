"""Top navigation bar — dynamically built from enabled modules."""
import streamlit as st
from shared.timing import measure
from db.models import modules_enabled_for_project
from auth.session import current_project_id

# module_key → nav icon
MODULE_ICONS = {
    "dashboard": "📊",
    "schedule":  "📅",
    "approval":  "✍️",
    "execution": "📸",
    "outputs":   "📄",
    "ledger":    "📋",
}

# module_key → ACTIVE_PAGE name
MODULE_PAGE_MAP = {
    "dashboard": "대시보드",
    "schedule":  "신청",
    "approval":  "승인",
    "execution": "사진등록",
    "outputs":   "계획서",
    "ledger":    "대장",
}

# module_key → 버튼 표시 레이블 (라우팅과 별도 — 줄바꿈 포함 가능)
MODULE_DISPLAY_LABELS = {
    "dashboard": "대시\n보드",
    "execution": "사진\n등록",
    "approval":  "계획\n확정",
}


@measure("core.render_topnav")


def render_topnav(con):
    """Render horizontal top navigation bar based on enabled modules."""
    active_page = st.session_state.get("ACTIVE_PAGE", "홈")
    if active_page == "관리자":
        return  # hide topnav on admin page

    project_id = current_project_id()
    if not project_id:
        return

    is_admin = st.session_state.get("IS_ADMIN", False)
    enabled_modules = modules_enabled_for_project(con, project_id, is_admin=is_admin)
    if not enabled_modules:
        return

    nav_items = [("🏠\n\n홈", "홈")]
    for mod in enabled_modules:
        key = mod["module_key"]
        icon = MODULE_ICONS.get(key, "📄")
        page_name = MODULE_PAGE_MAP.get(key, key)
        display   = MODULE_DISPLAY_LABELS.get(key, page_name)
        nav_items.append((f"{icon}\n\n{display}", page_name))

    cols = st.columns(len(nav_items))
    for col, (label, page) in zip(cols, nav_items):
        with col:
            btn_type = "primary" if active_page == page else "secondary"
            if st.button(label, key=f"topnav_{page}", use_container_width=True, type=btn_type):
                st.session_state["ACTIVE_PAGE"] = page
                st.rerun()
