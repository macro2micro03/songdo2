"""Login and project selection pages (account-based auth)."""
import streamlit as st
from supabase import Client
from config import ROLES
from auth.session import (
    auth_login, auth_reset, user_create, project_has_users,
    request_password_reset, verify_reset_and_update,
)
from db.models import project_list, project_get, project_create, modules_for_project, module_toggle


# ── 공통 헤더 ──────────────────────────────────────────────────────────────

def _login_header(project_name: str, subtitle: str) -> None:
    st.markdown(f"""
    <div style="text-align:center; padding:16px 0 8px 0;">
      <h3 style="color:var(--primary-700);display:flex;align-items:center;
                 justify-content:center;gap:6px;">
        <img src="data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAxMDAgMTE1Ij4KICA8ZWxsaXBzZSBjeD0iNTAiIGN5PSIxMDQiIHJ4PSIyNiIgcnk9IjExIiBmaWxsPSIjMWE0ZmM0Ii8+CiAgPHBhdGggZD0iTTUwIDQKICAgIEMyOSA0IDEyIDIxIDEyIDQyCiAgICBDMTIgNjAgMzAgNzggNDIgOTIKICAgIEM0NSA5NiA1MCAxMDIgNTAgMTAyCiAgICBDNTAgMTAyIDU1IDk2IDU4IDkyCiAgICBDNzAgNzggODggNjAgODggNDIKICAgIEM4OCAyMSA3MSA0IDUwIDQgWiIKICAgIGZpbGw9IiMyOWI2ZjYiLz4KICA8Y2lyY2xlIGN4PSI1MCIgY3k9IjQwIiByPSIxOCIgZmlsbD0id2hpdGUiLz4KPC9zdmc+Cg=="
             style="height:1.1em;width:auto;vertical-align:middle;" />
        {project_name}
      </h3>
      <p style="color:var(--text-muted); font-size:13px;">{subtitle}</p>
    </div>
    """, unsafe_allow_html=True)


# ── 프로젝트 선택 ─────────────────────────────────────────────────────────

def page_project_select(con: Client):
    """Project selection screen — Step 1."""
    st.markdown("""
    <div style="text-align:center; padding:24px 0 16px 0;">
      <div style="display:inline-block;">
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 72" width="160" height="72">
          <!-- 화물차 (오른쪽) -->
          <!-- 차체 -->
          <rect x="62" y="18" width="76" height="34" rx="3" fill="#1e3a8a"/>
          <!-- 캡 -->
          <rect x="118" y="24" width="20" height="22" rx="3" fill="#2563eb"/>
          <!-- 캡 창문 -->
          <rect x="121" y="27" width="14" height="11" rx="2" fill="#bfdbfe"/>
          <!-- 화물 적재함 -->
          <rect x="64" y="20" width="52" height="28" rx="2" fill="#3b82f6"/>
          <!-- 화물 박스들 -->
          <rect x="67" y="24" width="14" height="12" rx="1" fill="#fbbf24"/>
          <rect x="83" y="24" width="14" height="12" rx="1" fill="#f59e0b"/>
          <rect x="99" y="24" width="14" height="12" rx="1" fill="#fbbf24"/>
          <!-- 바퀴 -->
          <circle cx="82" cy="54" r="8" fill="#1e293b"/>
          <circle cx="82" cy="54" r="4" fill="#94a3b8"/>
          <circle cx="126" cy="54" r="8" fill="#1e293b"/>
          <circle cx="126" cy="54" r="4" fill="#94a3b8"/>
          <!-- 지면 -->
          <line x1="0" y1="62" x2="160" y2="62" stroke="#cbd5e1" stroke-width="1.5"/>
          <!-- 지게차 (왼쪽, 화물차 쪽으로 접근 중) -->
          <!-- 차체 -->
          <rect x="8" y="30" width="36" height="24" rx="3" fill="#f59e0b"/>
          <!-- 운전석 -->
          <rect x="28" y="22" width="16" height="16" rx="2" fill="#fbbf24"/>
          <!-- 창문 -->
          <rect x="30" y="24" width="12" height="9" rx="1" fill="#bfdbfe"/>
          <!-- 마스트(포크 기둥) -->
          <rect x="6" y="14" width="4" height="40" rx="1" fill="#d97706"/>
          <!-- 포크 -->
          <rect x="2" y="30" width="8" height="3" rx="1" fill="#92400e"/>
          <rect x="2" y="36" width="8" height="3" rx="1" fill="#92400e"/>
          <!-- 포크 위 박스 -->
          <rect x="2" y="18" width="14" height="12" rx="1" fill="#fbbf24" stroke="#d97706" stroke-width="1"/>
          <!-- 바퀴 -->
          <circle cx="18" cy="55" r="7" fill="#1e293b"/>
          <circle cx="18" cy="55" r="3.5" fill="#94a3b8"/>
          <circle cx="38" cy="55" r="7" fill="#1e293b"/>
          <circle cx="38" cy="55" r="3.5" fill="#94a3b8"/>
          <!-- 화살표 (접근 방향) -->
          <path d="M50 40 L60 40" stroke="#ef4444" stroke-width="2.5" stroke-dasharray="3,2" marker-end="url(#arr)"/>
          <defs>
            <marker id="arr" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
              <path d="M0,0 L0,6 L6,3 Z" fill="#ef4444"/>
            </marker>
          </defs>
        </svg>
      </div>
      <h2 style="margin:8px 0 4px 0; color:var(--primary-700);">자재 반출입 스케줄 관리</h2>
      <p style="color:var(--text-muted); font-size:13px;">프로젝트를 선택하세요</p>
    </div>
    """, unsafe_allow_html=True)

    projects = project_list(con)

    with st.container(key="proj_select_wrap"):
        if projects:
            project_names = [p["name"] for p in projects]
            col_sel, col_btn = st.columns([8.8, 1.2])
            with col_sel:
                selected = st.selectbox(
                    "프로젝트 선택",
                    project_names,
                    index=None,
                    placeholder="프로젝트 선택",
                    label_visibility="collapsed",
                    key="proj_select_box",
                )
            with col_btn:
                if st.button("▶", key="proj_go_btn", type="primary"):
                    if selected:
                        proj = next(p for p in projects if p["name"] == selected)
                        st.session_state["PROJECT_ID"]   = proj["id"]
                        st.session_state["PROJECT_NAME"] = proj["name"]
                        st.rerun()
                    else:
                        st.toast("프로젝트를 선택하세요.", icon="⚠️")
        else:
            st.info("등록된 프로젝트가 없습니다. 새 프로젝트를 생성하세요.")

    with st.container(key="proj_new_wrap"):
        with st.expander("＋ 새 프로젝트 만들기"):
            new_name = st.text_input("프로젝트명*", key="new_proj_name")
            new_desc = st.text_input("설명", key="new_proj_desc")
            c1, c2 = st.columns(2)
            with c1:
                new_site_pin = st.text_input("현장 PIN*", value="1234", key="new_proj_pin")
            with c2:
                new_admin_pin = st.text_input("Admin PIN*", value="9999", key="new_proj_admin_pin")
            if st.button("프로젝트 생성", type="primary", key="create_proj"):
                if not new_name.strip():
                    st.error("프로젝트명을 입력하세요.")
                else:
                    pid = project_create(con, new_name.strip(), new_desc.strip(),
                                         new_site_pin, new_admin_pin)
                    st.success(f"프로젝트 생성 완료: {new_name}")
                    st.session_state["PROJECT_ID"]   = pid
                    st.session_state["PROJECT_NAME"] = new_name.strip()
                    st.rerun()


# ── 로그인 폼 ─────────────────────────────────────────────────────────────

def _page_login_form(con: Client, project_id: str, project_name: str) -> None:
    # 전체 인증 UI 를 단일 placeholder 에 담아, 전환 직전 .empty() 로
    # DOM 을 명시적으로 비워야 Cloud frontend 에서 폼 잔상이 남지 않음.
    _page_area = st.empty()
    with _page_area.container():
        _login_header(project_name, "아이디와 비밀번호를 입력하세요")
        st.markdown("""
        <style>
        .st-key-back_to_proj_login button {
            min-height: 0 !important;
            height: 32px !important;
            padding: 0 12px !important;
            border-radius: 0.5rem !important;
            border: none !important;
            display: inline-flex !important;
            align-items: center !important;
            justify-content: center !important;
        }
        .st-key-back_to_proj_login button p {
            line-height: 1 !important;
            margin: 0 !important;
            padding: 0 !important;
        }
        </style>
        """, unsafe_allow_html=True)

        projects = project_list(con)
        if len(projects) > 1:
            if st.button("← 다른 프로젝트 선택", key="back_to_proj_login"):
                st.session_state.pop("PROJECT_ID", None)
                st.session_state.pop("PROJECT_NAME", None)
                _page_area.empty()
                st.rerun()

        with st.container(key="login_form_wrap"):
            with st.form("login_form"):
                username = st.text_input("아이디 *", placeholder="등록한 아이디 입력")
                password = st.text_input("비밀번호 *", type="password")
                submitted = st.form_submit_button("로그인", type="primary", use_container_width=True)

            if submitted:
                if not username.strip() or not password:
                    st.error("아이디와 비밀번호를 모두 입력하세요.")
                else:
                    ok, msg = auth_login(con, username, password)
                    if ok:
                        from auth.session import make_session_token
                        st.query_params["_s"] = make_session_token(
                            username.strip(), project_id
                        )
                        _page_area.empty()
                        st.rerun()
                    st.error(msg)

        # 비밀번호 찾기 링크 (로그인 폼 바로 아래)
        with st.container(key="login_forgot_pw"):
            st.markdown("""
            <style>
            .st-key-login_forgot_pw button {
                background: transparent !important;
                border: none !important;
                color: #64748b !important;
                font-size: 13px !important;
                min-height: 0 !important;
                padding: 8px 0 !important;
                text-decoration: underline !important;
            }
            .st-key-login_forgot_pw button:hover {
                color: var(--primary-700) !important;
            }
            </style>
            """, unsafe_allow_html=True)
            if st.button("비밀번호를 잊으셨나요?", key="go_reset", use_container_width=True):
                st.session_state["auth_mode"] = "reset"
                st.session_state.pop("reset_step", None)
                st.session_state.pop("reset_email", None)
                _page_area.empty()
                st.rerun()

        with st.container(key="login_signup_btn"):
            st.markdown(
                '<div style="text-align:center;padding-top:14px;font-size:13px;color:#64748b;">'
                '계정이 없으신가요?</div>'
                '<div style="height:12px;"></div>',
                unsafe_allow_html=True,
            )
            st.markdown("""
            <style>
            .st-key-login_signup_btn button {
                display: flex !important;
                align-items: center !important;
                justify-content: center !important;
            }
            .st-key-login_signup_btn button p {
                line-height: 1 !important;
                margin: 0 !important;
                padding: 0 !important;
            }
            </style>
            """, unsafe_allow_html=True)
            if st.button("회원가입", key="go_signup", use_container_width=True):
                st.session_state["auth_mode"] = "signup"
                _page_area.empty()
                st.rerun()


# ── 회원가입 폼 ───────────────────────────────────────────────────────────

def _page_signup_form(con: Client, project_id: str, project_name: str) -> None:
    _page_area = st.empty()
    with _page_area.container():
        _login_header(project_name, "계정을 만들어 서비스를 이용하세요")
        st.markdown("""
        <style>
        .st-key-back_to_login button {
            min-height: 0 !important;
            height: 32px !important;
            padding: 0 12px !important;
            border-radius: 0.5rem !important;
            border: none !important;
            display: inline-flex !important;
            align-items: center !important;
            justify-content: center !important;
        }
        .st-key-signup_form_wrap [data-testid="stExpander"] summary {
            min-height: 0 !important;
            height: auto !important;
            padding: 9px 0.75rem !important;
            line-height: 1.2 !important;
        }
        .st-key-signup_form_wrap [data-testid="stExpander"] summary span,
        .st-key-signup_form_wrap [data-testid="stExpander"] summary p {
            margin: 0 !important;
            padding: 0 !important;
            line-height: 1.2 !important;
            vertical-align: middle !important;
        }
        .st-key-signup_form_wrap [data-testid="stExpander"] {
            margin-bottom: 24px !important;
        }
        .st-key-back_to_login button p {
            line-height: 1 !important;
            margin: 0 !important;
            padding: 0 !important;
        }
        </style>
        """, unsafe_allow_html=True)

        if st.button("← 로그인으로 돌아가기", key="back_to_login"):
            st.session_state["auth_mode"] = "login"
            _page_area.empty()
            st.rerun()

        project = project_get(con, project_id) or {}
        expected_admin_pin = project.get("admin_pin", "")

        with st.container(key="signup_form_wrap"):
            with st.form("signup_form", clear_on_submit=False):
                username     = st.text_input("아이디 *", placeholder="영문·숫자 조합 (로그인 시 사용)")
                email        = st.text_input("이메일 *", placeholder="비밀번호 찾기 시 사용됩니다")
                name         = st.text_input("이름/직책 *", placeholder="예) 김삼성/건축시공")
                company_name = st.text_input("업체명 *", placeholder="예) OO내장, OO설비")
                role         = st.selectbox("구분 *", ROLES, index=None, placeholder="소속 구분 선택")

                st.markdown("---")
                pw1 = st.text_input("비밀번호 *", type="password", placeholder="6자 이상")
                pw2 = st.text_input("비밀번호 확인 *", type="password")

                # 관리자 계정 신청 (선택)
                with st.expander("🔐 관리자 계정 신청 (선택)"):
                    admin_pin_input = st.text_input(
                        "Admin PIN", type="password",
                        placeholder="관리자 PIN 입력 시 관리자 권한 부여",
                        key="signup_admin_pin",
                    )

                submitted = st.form_submit_button("가입하기", type="primary", use_container_width=True)

            if submitted:
                errors = []
                if not username.strip():     errors.append("아이디")
                if not email.strip():        errors.append("이메일")
                if not name.strip():         errors.append("이름/직책")
                if not company_name.strip(): errors.append("업체명")
                if not role:                 errors.append("구분")
                if not pw1:                errors.append("비밀번호")
                if pw1 != pw2:
                    st.error("비밀번호가 일치하지 않습니다.")
                    return
                if errors:
                    st.error(f"필수 입력 항목을 확인하세요: {', '.join(errors)}")
                    return

                is_admin = bool(admin_pin_input and admin_pin_input == expected_admin_pin)
                if admin_pin_input and not is_admin:
                    st.error("Admin PIN이 올바르지 않습니다.")
                    return

                ok, msg = user_create(con, project_id, username, pw1, name, role,
                                      is_admin, company_name, email)
                if ok:
                    st.toast(f"✅ {msg}", icon="✅")
                    st.session_state["auth_mode"] = "login"
                    _page_area.empty()
                    st.rerun()
                else:
                    st.error(msg)


# ── 비밀번호 재설정 폼 (이메일 OTP) ─────────────────────────────────────

def _page_reset_form(con: Client, project_id: str, project_name: str) -> None:
    _page_area = st.empty()
    with _page_area.container():
        _login_header(project_name, "가입 시 등록한 이메일로 인증 코드를 보내드립니다")
        st.markdown("""
        <style>
        .st-key-back_to_login_from_reset button {
            min-height: 0 !important;
            height: 32px !important;
            padding: 0 12px !important;
            border-radius: 0.5rem !important;
            border: none !important;
            display: inline-flex !important;
            align-items: center !important;
            justify-content: center !important;
        }
        .st-key-back_to_login_from_reset button p {
            line-height: 1 !important;
            margin: 0 !important;
            padding: 0 !important;
        }
        </style>
        """, unsafe_allow_html=True)

        if st.button("← 로그인으로 돌아가기", key="back_to_login_from_reset"):
            st.session_state["auth_mode"] = "login"
            st.session_state.pop("reset_step", None)
            st.session_state.pop("reset_email", None)
            _page_area.empty()
            st.rerun()

        step = st.session_state.get("reset_step", "request")

        # ── Step 1: 아이디 입력 → 메일 발송 ────────────────────────────────
        if step == "request":
            with st.container(key="reset_request_wrap"):
                with st.form("reset_request_form"):
                    username = st.text_input(
                        "아이디 *", placeholder="가입한 아이디 입력",
                        key="reset_username",
                    )
                    submitted = st.form_submit_button(
                        "인증 코드 받기", type="primary", use_container_width=True,
                    )

                if submitted:
                    if not username.strip():
                        st.error("아이디를 입력하세요.")
                    else:
                        ok, msg, email = request_password_reset(con, project_id, username)
                        if ok:
                            st.session_state["reset_step"]  = "verify"
                            st.session_state["reset_email"] = email
                            st.toast(msg, icon="📧")
                            _page_area.empty()
                            st.rerun()
                        else:
                            st.error(msg)
            return

        # ── Step 2: 코드 + 새 비번 입력 ──────────────────────────────────
        email = st.session_state.get("reset_email", "")
        masked = _mask_email(email)
        st.info(f"📧 {masked} 으로 발송된 8자리 코드를 입력하세요.")

        with st.container(key="reset_verify_wrap"):
            with st.form("reset_verify_form"):
                token = st.text_input(
                    "인증 코드 *", placeholder="메일로 받은 8자리 숫자",
                    max_chars=10, key="reset_token",
                )
                pw1 = st.text_input("새 비밀번호 *", type="password",
                                    placeholder="6자 이상", key="reset_pw1")
                pw2 = st.text_input("새 비밀번호 확인 *", type="password",
                                    key="reset_pw2")
                submitted = st.form_submit_button(
                    "비밀번호 변경", type="primary", use_container_width=True,
                )

            if submitted:
                if pw1 != pw2:
                    st.error("새 비밀번호가 일치하지 않습니다.")
                elif not token.strip():
                    st.error("인증 코드를 입력하세요.")
                else:
                    ok, msg = verify_reset_and_update(con, email, token, pw1)
                    if ok:
                        st.toast(msg, icon="✅")
                        st.session_state["auth_mode"] = "login"
                        st.session_state.pop("reset_step", None)
                        st.session_state.pop("reset_email", None)
                        _page_area.empty()
                        st.rerun()
                    else:
                        st.error(msg)

        with st.container(key="reset_resend_wrap"):
            st.markdown(
                '<div style="text-align:center;padding-top:14px;font-size:13px;color:#64748b;">'
                '코드를 받지 못하셨나요?</div>'
                '<div style="height:8px;"></div>',
                unsafe_allow_html=True,
            )
            if st.button("다른 아이디로 다시 시도", key="reset_restart",
                         use_container_width=True):
                st.session_state["reset_step"] = "request"
                st.session_state.pop("reset_email", None)
                _page_area.empty()
                st.rerun()


def _mask_email(email: str) -> str:
    """이메일 표시용 마스킹 — 'jo***@gmail.com' 형태."""
    if not email or "@" not in email:
        return email
    local, _, domain = email.partition("@")
    if len(local) <= 2:
        return f"{local[:1]}***@{domain}"
    return f"{local[:2]}***@{domain}"


# ── 메인 진입점 ───────────────────────────────────────────────────────────

def page_login(con: Client):
    """Authentication screen (account-based)."""
    project_id   = st.session_state.get("PROJECT_ID", "")
    project_name = st.session_state.get("PROJECT_NAME", "프로젝트")

    if "auth_mode" not in st.session_state:
        st.session_state["auth_mode"] = "login"

    mode = st.session_state["auth_mode"]
    if mode == "signup":
        _page_signup_form(con, project_id, project_name)
    elif mode == "reset":
        _page_reset_form(con, project_id, project_name)
    else:
        _page_login_form(con, project_id, project_name)
