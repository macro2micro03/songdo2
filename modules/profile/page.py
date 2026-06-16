"""내 정보 수정 페이지."""
import streamlit as st
from shared.timing import measure
from supabase import Client

from shared.helpers import now_str
from auth.session import _hash_pw, _new_salt
from config import ROLES


@measure("page.profile")


def page_profile(con: Client):
    st.markdown("""
    <style>
    .st-key-profile_wrap [data-testid="stWidgetLabel"],
    .st-key-profile_wrap label {
        margin-bottom: -14px !important;
        padding-bottom: 0 !important;
        line-height: 1 !important;
    }
    .st-key-profile_wrap [data-testid="stElementContainer"] {
        margin-bottom: 16px !important;
    }
    </style>
    """, unsafe_allow_html=True)

    st.markdown("### 👤 내 정보 수정")

    project_id = st.session_state.get("PROJECT_ID", "")
    username   = st.session_state.get("USER_ID", "")
    user_name  = st.session_state.get("USER_NAME", "")

    # username으로 먼저 조회, 없으면 name으로 조회
    res = (con.table("profiles").select("*")
           .eq("project_id", project_id).eq("username", username)
           .limit(1).execute())
    if not res.data:
        res = (con.table("profiles").select("*")
               .eq("project_id", project_id).eq("name", user_name)
               .limit(1).execute())
    user = res.data[0] if res.data else {}
    if not user:
        st.error("계정 정보를 불러올 수 없습니다.")
        return

    with st.container(key="profile_wrap"):
        st.markdown("#### 기본 정보")
        new_name    = st.text_input("이름/직책 *", value=user.get("name", ""))
        new_company = st.text_input("업체명 *", value=user.get("company_name", ""))
        new_role    = st.selectbox("구분 *", ROLES,
                                   index=ROLES.index(user["role"]) if user.get("role") in ROLES else 0)

        st.markdown("#### 비밀번호 변경 (변경 시에만 입력)")
        cur_pw  = st.text_input("현재 비밀번호", type="password")
        new_pw1 = st.text_input("새 비밀번호", type="password", placeholder="6자 이상")
        new_pw2 = st.text_input("새 비밀번호 확인", type="password")

        if st.button("저장", type="primary", use_container_width=True):
            errors = []
            if not new_name.strip():    errors.append("이름/직책")
            if not new_company.strip(): errors.append("업체명")
            if errors:
                st.error(f"필수 항목을 입력하세요: {', '.join(errors)}")
                return

            # 비밀번호 변경 요청 시 검증
            if cur_pw or new_pw1 or new_pw2:
                if _hash_pw(cur_pw, user["salt"]) != user["password_hash"]:
                    st.error("현재 비밀번호가 올바르지 않습니다.")
                    return
                if not new_pw1:
                    st.error("새 비밀번호를 입력하세요.")
                    return
                if len(new_pw1) < 6:
                    st.error("비밀번호는 6자 이상이어야 합니다.")
                    return
                if new_pw1 != new_pw2:
                    st.error("새 비밀번호가 일치하지 않습니다.")
                    return
                new_salt = _new_salt()
                new_hash = _hash_pw(new_pw1, new_salt)
                con.table("profiles").update({
                    "name": new_name.strip(),
                    "company_name": new_company.strip(),
                    "role": new_role,
                    "password_hash": new_hash,
                    "salt": new_salt,
                    "updated_at": now_str(),
                }).eq("id", user["id"]).execute()
            else:
                con.table("profiles").update({
                    "name": new_name.strip(),
                    "company_name": new_company.strip(),
                    "role": new_role,
                    "updated_at": now_str(),
                }).eq("id", user["id"]).execute()

            # 세션 업데이트
            st.session_state["USER_NAME"]    = new_name.strip()
            st.session_state["USER_COMPANY"] = new_company.strip()
            st.session_state["USER_ROLE"]    = new_role
            st.toast("내 정보가 저장되었습니다.", icon="✅")
            st.session_state["ACTIVE_PAGE"] = "홈"
            st.rerun()
