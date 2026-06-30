"""Admin settings page."""

import json

import streamlit as st
from shared.timing import measure
from supabase import Client

from config import DEFAULT_SITE_NAME, DEFAULT_SITE_PIN, DEFAULT_ADMIN_PIN, ROLES
from db.models import settings_get, settings_set
from modules.approval.crud import routing_get
from modules.admin.module_manager import render_module_manager


@measure("page.admin")


def page_admin(con: Client):
    st.markdown("""
    <style>
    .st-key-admin_wrap [data-testid="stWidgetLabel"],
    .st-key-admin_wrap label {
        margin-bottom: -14px !important;
        padding-bottom: 0 !important;
        line-height: 1 !important;
    }
    .st-key-admin_wrap [data-testid="stElementContainer"] {
        margin-bottom: 16px !important;
    }
    </style>
    """, unsafe_allow_html=True)
    st.markdown("### 🛠 관리자 설정")
    if not st.session_state.get("IS_ADMIN", False):
        st.warning("관리자 모드로 로그인해야 합니다.")
        return

    with st.container(key="admin_wrap"):
        st.markdown("#### ⚙️ 현장 설정")
        site_name = st.text_input("현장명", value=settings_get(con, "site_name", DEFAULT_SITE_NAME))
        site_pin = st.text_input("현장 PIN", value=settings_get(con, "site_pin", DEFAULT_SITE_PIN))
        admin_pin = st.text_input("Admin PIN", value=settings_get(con, "admin_pin", DEFAULT_ADMIN_PIN))

        st.markdown("---")

        st.markdown("#### 📅 스케줄 입력 가능 기간")
        _sched_days = int(settings_get(con, "schedule_advance_days", "2"))
        sched_advance_days = st.number_input(
            "협력사 입력 가능 일수 (오늘 포함 +N일)",
            min_value=0, max_value=30, value=_sched_days, step=1,
            help="0 = 오늘만, 2 = 오늘·내일·모레 (기본값: 2)"
        )

        st.markdown("---")

        st.markdown("#### 🔄 승인 라우팅")
        routing = routing_get(con)
        in_default  = [r for r in routing.get("IN",  []) if r in ROLES]
        out_default = [r for r in routing.get("OUT", []) if r in ROLES]
        in_route  = st.multiselect("반입(IN) 승인순서",  options=ROLES, default=in_default)
        out_route = st.multiselect("반출(OUT) 승인순서", options=ROLES, default=out_default)

        if st.button("저장", type="primary", use_container_width=True):
            new_site_name = site_name.strip() or DEFAULT_SITE_NAME
            settings_set(con, "site_name", new_site_name)
            settings_set(con, "site_pin", site_pin.strip() or DEFAULT_SITE_PIN)
            settings_set(con, "admin_pin", admin_pin.strip() or DEFAULT_ADMIN_PIN)
            settings_set(con, "approval_routing_json", json.dumps({"IN": in_route, "OUT": out_route}, ensure_ascii=False))
            settings_set(con, "schedule_advance_days", str(int(sched_advance_days)))
            st.session_state["PROJECT_NAME"] = new_site_name
            st.success("저장 완료")
            st.rerun()

    st.markdown("---")

    # ── 터미널 설정 ────────────────────────────────────────────────────
    st.markdown("#### 🚧 터미널 설정")
    st.caption("신청 탭 예약 폼에서 선택할 터미널(반출입 장소) 목록입니다.")
    _zones_raw = settings_get(con, "gate_zones_json", "[]")
    try:
        _zones: list = json.loads(_zones_raw)
    except Exception:
        _zones = []

    _disabled_raw = settings_get(con, "gate_zones_disabled_json", "[]")
    try:
        _disabled: list = json.loads(_disabled_raw)
    except Exception:
        _disabled = []

    if _zones:
        st.caption("등록된 터미널 · 토글로 활성/비활성 전환, 삭제 버튼으로 제거")
        st.markdown("""<style>
        [class*="st-key-zone_row_"] .stHorizontalBlock {
            align-items: center !important;
            flex-wrap: nowrap !important;
            gap: 8px !important;
        }
        [class*="st-key-zone_row_"] .stHorizontalBlock > [data-testid="stColumn"]:nth-child(1) {
            flex: 1 1 0 !important; min-width: 0 !important;
        }
        [class*="st-key-zone_row_"] .stHorizontalBlock > [data-testid="stColumn"]:nth-child(2),
        [class*="st-key-zone_row_"] .stHorizontalBlock > [data-testid="stColumn"]:nth-child(3) {
            flex: 0 0 52px !important; min-width: 52px !important; max-width: 52px !important;
        }
        [class*="st-key-edit_zone_"] button {
            background-color: #2563eb !important;
            border-color: #2563eb !important;
            border-radius: 4px !important;
            height: 32px !important; min-height: 32px !important;
            padding: 0 8px !important;
            display: flex !important; align-items: center !important; justify-content: center !important;
        }
        [class*="st-key-edit_zone_"] button:hover { background-color: #1d4ed8 !important; border-color: #1d4ed8 !important; }
        [class*="st-key-edit_zone_"] button,
        [class*="st-key-edit_zone_"] button p,
        [class*="st-key-edit_zone_"] button span,
        [class*="st-key-edit_zone_"] button div {
            color: #f8f8f8 !important; font-size: 11px !important;
            line-height: 1 !important; margin: 0 !important; padding: 0 !important;
        }
        [class*="st-key-zone_edit_save_"] button,
        [class*="st-key-zone_edit_cancel_"] button {
            height: 32px !important; min-height: 32px !important;
            padding: 0 6px !important;
            display: flex !important; align-items: center !important; justify-content: center !important;
            white-space: nowrap !important;
        }
        [class*="st-key-zone_edit_save_"] button p,
        [class*="st-key-zone_edit_cancel_"] button p,
        [class*="st-key-zone_edit_save_"] button span,
        [class*="st-key-zone_edit_cancel_"] button span,
        [class*="st-key-zone_edit_save_"] button div,
        [class*="st-key-zone_edit_cancel_"] button div {
            font-size: 11px !important;
            line-height: 1 !important; margin: 0 !important; padding: 0 !important;
            white-space: nowrap !important;
        }
        [class*="st-key-zone_row_"] [data-testid="stElementContainer"] {
            margin: 0 !important; padding: 0 !important;
        }
        [class*="st-key-zone_toggle_"] label {
            font-size: 14px !important;
            color: #0f172a !important;
        }
        [class*="st-key-zone_toggle_"] label p {
            font-size: 14px !important;
            margin: 0 !important;
        }
        [class*="st-key-del_zone_"] button {
            background-color: #b91c1c !important;
            border-color: #b91c1c !important;
            border-radius: 4px !important;
            height: 32px !important; min-height: 32px !important;
            padding: 0 8px !important;
            display: flex !important; align-items: center !important; justify-content: center !important;
        }
        [class*="st-key-del_zone_"] button:hover { background-color: #991b1b !important; border-color: #991b1b !important; }
        [class*="st-key-del_zone_"] button,
        [class*="st-key-del_zone_"] button p,
        [class*="st-key-del_zone_"] button span,
        [class*="st-key-del_zone_"] button div {
            color: #f8f8f8 !important; font-size: 11px !important;
            line-height: 1 !important; margin: 0 !important; padding: 0 !important;
        }
        </style>""", unsafe_allow_html=True)
        for i, z in enumerate(_zones):
            is_disabled = z in _disabled
            _badge = "  ⚠️비활성" if is_disabled else ""
            _editing = st.session_state.get("zone_edit_idx") == i
            with st.container(key=f"zone_row_{i}"):
                if _editing:
                    ec1, ec2, ec3 = st.columns([4, 1.2, 1.2])
                    with ec1:
                        new_name = st.text_input("새 이름", value=z, key=f"zone_edit_input_{i}",
                                                 label_visibility="collapsed")
                    with ec2:
                        if st.button("저장", key=f"zone_edit_save_{i}", use_container_width=True):
                            nn = new_name.strip()
                            if nn and nn != z:
                                if nn in _zones:
                                    st.warning(f"'{nn}'은 이미 등록되어 있습니다.")
                                else:
                                    _zones[i] = nn
                                    if z in _disabled:
                                        _disabled = [nn if d == z else d for d in _disabled]
                                    settings_set(con, "gate_zones_json", json.dumps(_zones, ensure_ascii=False))
                                    settings_set(con, "gate_zones_disabled_json", json.dumps(_disabled, ensure_ascii=False))
                                    # 기존 저장된 요청/스케줄의 터미널 값도 함께 변경
                                    con.table("requests").update({"gate": nn}).eq("gate", z).execute()
                                    con.table("schedules").update({"gate": nn}).eq("gate", z).execute()
                                    st.session_state.pop("zone_edit_idx", None)
                                    st.success(f"'{z}' → '{nn}' 으로 변경 완료 (기존 데이터 포함)")
                                    st.rerun()
                            else:
                                st.session_state.pop("zone_edit_idx", None)
                                st.rerun()
                    with ec3:
                        if st.button("취소", key=f"zone_edit_cancel_{i}", use_container_width=True):
                            st.session_state.pop("zone_edit_idx", None)
                            st.rerun()
                else:
                    zc1, zc2, zc3 = st.columns([5, 1, 1])
                    with zc1:
                        active = st.toggle(f"{z}{_badge}", value=not is_disabled,
                                           key=f"zone_toggle_{i}")
                        if active == is_disabled:
                            if active:
                                _disabled = [d for d in _disabled if d != z]
                            else:
                                if z not in _disabled:
                                    _disabled.append(z)
                            settings_set(con, "gate_zones_disabled_json", json.dumps(_disabled, ensure_ascii=False))
                            st.rerun()
                    with zc2:
                        if st.button("수정", key=f"edit_zone_{i}", use_container_width=True):
                            st.session_state["zone_edit_idx"] = i
                            st.rerun()
                    with zc3:
                        if st.button("삭제", key=f"del_zone_{i}", use_container_width=True):
                            _zones.pop(i)
                            _disabled = [d for d in _disabled if d != z]
                            settings_set(con, "gate_zones_json", json.dumps(_zones, ensure_ascii=False))
                            settings_set(con, "gate_zones_disabled_json", json.dumps(_disabled, ensure_ascii=False))
                            st.rerun()
    else:
        st.caption("등록된 터미널이 없습니다.")

    st.markdown("""<style>
    .st-key-zone_add_wrap [data-testid="stForm"] {
        padding-bottom: 4px !important;
    }
    </style>""", unsafe_allow_html=True)
    with st.container(key="zone_add_wrap"):
        with st.form("zone_add_form", clear_on_submit=True):
            zf1, zf2 = st.columns([5, 1])
            with zf1:
                new_zone = st.text_input("새 터미널 추가", placeholder="예) A터미널, 101동 앞, 정문 하역장")
            with zf2:
                st.markdown("<div style='margin-top:28px'></div>", unsafe_allow_html=True)
                add_zone = st.form_submit_button("추가", use_container_width=True)
            if add_zone:
                nz = new_zone.strip()
                if nz and nz not in _zones:
                    _zones.append(nz)
                    settings_set(con, "gate_zones_json", json.dumps(_zones, ensure_ascii=False))
                    st.rerun()
                elif nz in _zones:
                    st.warning(f"'{nz}'은 이미 등록되어 있습니다.")

    # ── 터미널 사용 예약존 ────────────────────────────────────────────────
    st.markdown("##### 터미널 드롭다운 사용 예약존")
    st.caption("선택된 예약존에서만 신청 폼에 터미널 선택이 표시됩니다.")
    try:
        _tz_active = [z for z in json.loads(settings_get(con, "booking_zones_json", '["A"]'))
                      if z not in json.loads(settings_get(con, "booking_zones_disabled_json", "[]"))]
    except Exception:
        _tz_active = []
    try:
        _tz_sel: list = json.loads(settings_get(con, "terminal_zones_json", '["A"]'))
    except Exception:
        _tz_sel = ["A"]
    _tz_default = [z for z in _tz_sel if z in _tz_active]
    _tz_new = st.multiselect("터미널 사용 존 선택", options=_tz_active, default=_tz_default,
                              key="terminal_zones_ms")
    if st.button("저장", key="terminal_zones_save", type="primary", use_container_width=True):
        settings_set(con, "terminal_zones_json", json.dumps(_tz_new, ensure_ascii=False))
        st.success("저장되었습니다.")
        st.rerun()

    # ── 터미널 기본 보관 기간 ─────────────────────────────────────────────
    st.markdown("##### 📦 터미널 기본 보관 기간")
    st.caption("반입일부터 며칠간 터미널을 점유로 볼지 기본값입니다. "
               "(계획 확정 시 저장 기간 산정 + 신청 화면 점유 표시·차단에 적용)")
    try:
        _sdd_cur = max(1, int(settings_get(con, "storage_default_days", "14")))
    except Exception:
        _sdd_cur = 14
    _sdd_new = st.number_input("기본 보관일수 (일)", min_value=1, max_value=180,
                               value=_sdd_cur, step=1, key="storage_default_days_inp")
    if int(_sdd_new) != _sdd_cur:
        settings_set(con, "storage_default_days", str(int(_sdd_new)))
        st.toast(f"기본 보관일수가 {int(_sdd_new)}일로 저장되었습니다.", icon="📦")
        st.rerun()

    st.markdown("---")

    # ── 예약존 설정 ────────────────────────────────────────────────────────
    st.markdown("#### 🏗️ 예약존 설정")
    st.caption("신청 탭에서 시간대별로 관리할 구역입니다. (예: A존, B존, 크레인1)")
    _bz_raw = settings_get(con, "booking_zones_json", '["A"]')
    try:
        _bzones: list = json.loads(_bz_raw)
    except Exception:
        _bzones = ["A"]
    _bz_dis_raw = settings_get(con, "booking_zones_disabled_json", "[]")
    try:
        _bz_disabled: list = json.loads(_bz_dis_raw)
    except Exception:
        _bz_disabled = []

    if _bzones:
        st.markdown("""<style>
        [class*="st-key-bzone_row_"] .stHorizontalBlock {
            align-items: center !important; flex-wrap: nowrap !important; gap: 8px !important;
        }
        [class*="st-key-bzone_row_"] .stHorizontalBlock > [data-testid="stColumn"]:nth-child(1) {
            flex: 1 1 0 !important; min-width: 0 !important;
        }
        [class*="st-key-bzone_row_"] .stHorizontalBlock > [data-testid="stColumn"]:nth-child(2) {
            flex: 0 0 52px !important; min-width: 52px !important; max-width: 52px !important;
        }
        [class*="st-key-bzone_row_"] [data-testid="stElementContainer"] { margin: 0 !important; padding: 0 !important; }
        [class*="st-key-bzone_toggle_"] label { font-size: 14px !important; color: #0f172a !important; }
        [class*="st-key-bzone_toggle_"] label p { font-size: 14px !important; margin: 0 !important; }
        [class*="st-key-del_bzone_"] button {
            background-color: #b91c1c !important; border-color: #b91c1c !important;
            border-radius: 4px !important; height: 32px !important; min-height: 32px !important;
            padding: 0 8px !important; display: flex !important; align-items: center !important; justify-content: center !important;
        }
        [class*="st-key-del_bzone_"] button:hover { background-color: #991b1b !important; }
        [class*="st-key-del_bzone_"] button,
        [class*="st-key-del_bzone_"] button p,
        [class*="st-key-del_bzone_"] button span {
            color: #f8f8f8 !important; font-size: 11px !important; line-height: 1 !important; margin: 0 !important; padding: 0 !important;
        }
        </style>""", unsafe_allow_html=True)
        for i, bz in enumerate(_bzones):
            is_bz_dis = bz in _bz_disabled
            _bz_badge = "  ⚠️비활성" if is_bz_dis else ""
            with st.container(key=f"bzone_row_{i}"):
                bc1, bc2 = st.columns([6, 1])
                with bc1:
                    bz_active = st.toggle(f"{bz}{_bz_badge}", value=not is_bz_dis, key=f"bzone_toggle_{i}")
                    if bz_active == is_bz_dis:
                        if bz_active:
                            _bz_disabled = [d for d in _bz_disabled if d != bz]
                        else:
                            if bz not in _bz_disabled:
                                _bz_disabled.append(bz)
                        settings_set(con, "booking_zones_disabled_json", json.dumps(_bz_disabled, ensure_ascii=False))
                        st.rerun()
                with bc2:
                    if st.button("삭제", key=f"del_bzone_{i}", use_container_width=True):
                        _bzones.pop(i)
                        _bz_disabled = [d for d in _bz_disabled if d != bz]
                        settings_set(con, "booking_zones_json", json.dumps(_bzones, ensure_ascii=False))
                        settings_set(con, "booking_zones_disabled_json", json.dumps(_bz_disabled, ensure_ascii=False))
                        st.rerun()
    else:
        st.caption("등록된 예약존이 없습니다.")

    with st.container(key="bzone_add_wrap"):
        with st.form("bzone_add_form", clear_on_submit=True):
            bf1, bf2 = st.columns([5, 1])
            with bf1:
                new_bzone = st.text_input("새 예약존 추가", placeholder="예) A존, 크레인1, 하역장")
            with bf2:
                st.markdown("<div style='margin-top:28px'></div>", unsafe_allow_html=True)
                add_bzone = st.form_submit_button("추가", use_container_width=True)
            if add_bzone:
                nbz = new_bzone.strip()
                if nbz and nbz not in _bzones:
                    _bzones.append(nbz)
                    settings_set(con, "booking_zones_json", json.dumps(_bzones, ensure_ascii=False))
                    st.rerun()
                elif nbz in _bzones:
                    st.warning(f"'{nbz}'은 이미 등록되어 있습니다.")

    st.markdown("---")

    # Module management section
    project_id = st.session_state.get("PROJECT_ID")
    if project_id:
        render_module_manager(con, project_id)
    else:
        st.caption("프로젝트를 선택하면 모듈 설정을 관리할 수 있습니다.")

    st.markdown("---")

    # ── 승인 서명 사용 (기능 모듈 설정 아래) ──────────────────────────────
    st.markdown("#### ✍️ 승인 서명")
    _sig_cur = settings_get(con, "signature_enabled", "true") != "false"
    _sig_new = st.toggle(
        "승인(계획 확정) 시 서명 사용",
        value=_sig_cur,
        help="끄면 계획 확정 화면에서 서명 입력이 사라지고, 승인자 이름이 정자로 자동 기록됩니다.",
        key="admin_sig_toggle",
    )
    if _sig_new != _sig_cur:
        settings_set(con, "signature_enabled", "true" if _sig_new else "false")
        st.toast("서명 사용 설정이 저장되었습니다.", icon="✍️")
        st.rerun()

    st.markdown("---")

    # ── 사용자 설정 변경 — 비밀번호 재설정 + 권한 관리 ────────────────────
    #
    # · 보안: IS_ADMIN 권한자만 진입 (페이지 상단 가드)
    # · 비밀번호 재설정: 분실 시 임시 비밀번호 부여 (첫 로그인 후 변경 안내)
    # · 관리자 권한 부여: 관리자 이상이면 가능
    # · 관리자 권한 해제: 시스템관리자만 가능
    # · 시스템관리자(is_sysadmin)는 앱에서 변경 불가 — DB/개발자 전용
    from auth.session import user_list, admin_reset_user_password, set_user_admin

    is_sysadmin = bool(st.session_state.get("IS_SYSADMIN", False))

    st.markdown("#### 👥 사용자 설정 변경")
    st.caption("비밀번호 재설정 및 관리자 권한을 관리합니다. "
               "관리자 권한 부여는 관리자 이상, 해제는 시스템관리자만 가능합니다.")

    my_username = st.session_state.get("USER_ID", "")
    _users = user_list(con, project_id) if project_id else []

    if not _users:
        st.info("등록된 사용자가 없습니다.")
    else:
        # 검색
        _q = st.text_input(
            "🔍 사용자 검색", key="pwreset_search",
            placeholder="아이디 또는 이름으로 필터",
        ).strip().lower()
        if _q:
            _users = [
                u for u in _users
                if _q in (u.get("username") or "").lower()
                or _q in (u.get("name") or "").lower()
            ]

        # CSS: 사용자 행 레이아웃
        st.markdown("""<style>
        [class*="st-key-pwreset_row_"] .stHorizontalBlock {
            align-items: center !important;
            flex-wrap: nowrap !important;
            gap: 8px !important;
            padding: 6px 0 !important;
            border-bottom: 1px solid var(--border-light, #e2e8f0) !important;
        }
        [class*="st-key-pwreset_row_"] .stHorizontalBlock > [data-testid="stColumn"]:nth-child(1) {
            flex: 1 1 0 !important; min-width: 0 !important;
        }
        [class*="st-key-pwreset_row_"] .stHorizontalBlock > [data-testid="stColumn"]:nth-child(2) {
            flex: 0 0 88px !important; min-width: 88px !important; max-width: 88px !important;
        }
        [class*="st-key-pwreset_row_"] [data-testid="stElementContainer"] {
            margin: 0 !important; padding: 0 !important;
        }
        [class*="st-key-pwreset_btn_"] button {
            background-color: #2563eb !important;
            border-color: #2563eb !important;
            border-radius: 4px !important;
            height: 32px !important; min-height: 32px !important;
            padding: 0 8px !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
        }
        [class*="st-key-pwreset_btn_"] button:hover {
            background-color: #1d4ed8 !important;
            border-color: #1d4ed8 !important;
        }
        [class*="st-key-pwreset_btn_"] button,
        [class*="st-key-pwreset_btn_"] button p,
        [class*="st-key-pwreset_btn_"] button span {
            color: #f8f8f8 !important;
            font-size: 12px !important;
            line-height: 1 !important;
            margin: 0 !important;
        }
        [class*="st-key-pwreset_form_"] {
            background: #fef3c7 !important;
            border: 1px solid #fbbf24 !important;
            border-radius: 6px !important;
            padding: 12px !important;
            margin: 8px 0 !important;
        }
        </style>""", unsafe_allow_html=True)

        if not _users:
            st.caption("검색 결과가 없습니다.")

        for u in _users:
            uid    = u["id"]
            uname  = u.get("username") or "—"
            nm     = u.get("name") or ""
            urole       = u.get("role") or ""
            u_is_sys    = bool(u.get("is_sysadmin"))
            u_is_admin  = bool(u.get("is_admin"))
            is_self     = bool(uname and uname == my_username)
            badges = []
            if u_is_sys:
                badges.append("👑시스템관리자")
            elif u_is_admin:
                badges.append("🔐관리자")
            if is_self:
                badges.append("본인")
            badge_txt = (" · " + " · ".join(badges)) if badges else ""

            short = uid[:8]
            with st.container(key=f"pwreset_row_{short}"):
                lc, rc = st.columns([6, 1])
                with lc:
                    st.markdown(
                        f"**{uname}** · {nm} ({urole}){badge_txt}"
                    )
                with rc:
                    if st.button("설정", key=f"pwreset_btn_{short}",
                                 use_container_width=True):
                        st.session_state["pwreset_target_id"]   = uid
                        st.session_state["pwreset_target_name"] = f"{uname} ({nm})"
                        # 이전 입력값 초기화
                        for _k in list(st.session_state.keys()):
                            if isinstance(_k, str) and (
                                _k.startswith("pwreset_new1_")
                                or _k.startswith("pwreset_new2_")
                            ):
                                st.session_state.pop(_k, None)
                        st.rerun()

            # 인라인 폼: 이 사용자가 선택된 경우에만 표시
            if st.session_state.get("pwreset_target_id") == uid:
                with st.container(key=f"pwreset_form_{short}"):
                    st.markdown(f"⚙ **{uname} ({nm})** 설정 변경")

                    # ── 권한 관리 ──────────────────────────────────────
                    st.markdown("**권한**")
                    if u_is_sys:
                        st.caption("👑 시스템관리자 — 권한 변경은 DB/개발자 전용입니다.")
                    elif is_self:
                        st.caption("본인 권한은 변경할 수 없습니다.")
                    elif u_is_admin:
                        # 관리자 → 해제 (시스템관리자만)
                        if is_sysadmin:
                            if st.button("🔓 관리자 권한 해제",
                                         key=f"perm_revoke_{short}",
                                         use_container_width=True):
                                ok, msg = set_user_admin(con, uid, False)
                                st.toast(f"✅ {uname} {msg}", icon="🔓")
                                st.rerun()
                        else:
                            st.caption("관리자 권한 해제는 시스템관리자만 가능합니다.")
                    else:
                        # 비관리자 → 부여 (관리자 이상)
                        if st.button("🔐 관리자 권한 부여",
                                     key=f"perm_grant_{short}",
                                     type="primary",
                                     use_container_width=True):
                            ok, msg = set_user_admin(con, uid, True)
                            st.toast(f"✅ {uname} {msg}", icon="🔐")
                            st.rerun()

                    st.markdown("---")

                    # ── 비밀번호 재설정 ────────────────────────────────
                    st.markdown("**비밀번호 재설정**")
                    if uname == my_username:
                        st.info(
                            "본인 비밀번호는 [내정보] 페이지에서 "
                            "현재 비밀번호 확인 후 변경하는 것을 권장합니다."
                        )
                    _np1 = st.text_input(
                        "새 임시 비밀번호 (6자 이상) *",
                        type="password",
                        key=f"pwreset_new1_{short}",
                        placeholder="임시 비밀번호 — 사용자에게 직접 전달",
                    )
                    _np2 = st.text_input(
                        "새 비밀번호 확인 *",
                        type="password",
                        key=f"pwreset_new2_{short}",
                    )
                    ac1, ac2 = st.columns(2)
                    with ac1:
                        if st.button("✓ 재설정 실행",
                                     key=f"pwreset_do_{short}",
                                     type="primary",
                                     use_container_width=True):
                            if not _np1 or len(_np1) < 6:
                                st.error("비밀번호는 6자 이상이어야 합니다.")
                            elif _np1 != _np2:
                                st.error("두 비밀번호가 일치하지 않습니다.")
                            else:
                                ok, msg = admin_reset_user_password(con, uid, _np1)
                                if ok:
                                    st.toast(
                                        f"✅ {uname} 비밀번호 재설정 완료",
                                        icon="🔐",
                                    )
                                    st.session_state.pop("pwreset_target_id", None)
                                    st.session_state.pop("pwreset_target_name", None)
                                    st.session_state.pop(f"pwreset_new1_{short}", None)
                                    st.session_state.pop(f"pwreset_new2_{short}", None)
                                    st.rerun()
                                else:
                                    st.error(msg)
                    with ac2:
                        if st.button("취소",
                                     key=f"pwreset_cancel_{short}",
                                     use_container_width=True):
                            st.session_state.pop("pwreset_target_id", None)
                            st.session_state.pop("pwreset_target_name", None)
                            st.session_state.pop(f"pwreset_new1_{short}", None)
                            st.session_state.pop(f"pwreset_new2_{short}", None)
                            st.rerun()
