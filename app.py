"""자재 반출입 관리 App. v3.0.0 — Entry Point.

Modular architecture with project-based authentication
and configurable feature modules.
"""
import html
from datetime import date
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
from core.css import inject_css
from core.header import ui_header
from core.nav import render_topnav
from core.pwa import inject_pwa
from core.sidebar import render_sidebar
from auth.session import session_has_project, session_is_authed
from auth.login import page_project_select, page_login
from modules.approval.page import page_approval
from modules.execution.page import page_execute
from modules.outputs.page import page_outputs
from modules.ledger.page import page_ledger
from modules.admin.page import page_admin
from modules.schedule.page import page_schedule
from modules.profile.page import page_profile
from modules.dashboard.page import page_dashboard
from shared.timing import clear_timings, render_panel, measure


# ── Page router ──
PAGE_ROUTER = {
    "대시보드":  page_dashboard,
    "신청":      page_schedule,
    "승인":      page_approval,
    "사진등록":  page_execute,
    "계획서":    page_outputs,
    "산출물":    page_outputs,
    "대장":      page_ledger,
    "관리자":    page_admin,
    "내정보":    page_profile,
}


def page_home(con):
    """Home page — imported here to avoid circular deps."""
    from modules.request.crud import req_list, req_delete
    from modules.approval.crud import approvals_inbox
    from modules.execution.crud import photos_for_req
    from config import KIND_IN
    from pathlib import Path
    from shared.helpers import today_str

    role      = st.session_state.get("USER_ROLE", "")
    is_admin  = st.session_state.get("IS_ADMIN", False)
    user_name = st.session_state.get("USER_NAME", "")

    st.markdown("""
    <style>
:root [class*="st-key-home_edit_"] button {
        background-color: #1d4ed8 !important;
        border-color: #1d4ed8 !important;
        border-radius: 4px !important;
    }
    :root [class*="st-key-home_edit_"] button:hover {
        background-color: #1e40af !important;
        border-color: #1e40af !important;
    }
    :root [class*="st-key-home_edit_"] button,
    :root [class*="st-key-home_edit_"] button p,
    :root [class*="st-key-home_edit_"] button * {
        color: #f8f8f8 !important;
    }
    :root [class*="st-key-home_del_"] button {
        background-color: #b91c1c !important;
        border-color: #b91c1c !important;
        border-radius: 4px !important;
    }
    :root [class*="st-key-home_del_"] button:hover {
        background-color: #991b1b !important;
        border-color: #991b1b !important;
    }
    :root [class*="st-key-home_del_"] button,
    :root [class*="st-key-home_del_"] button p,
    :root [class*="st-key-home_del_"] button span,
    :root [class*="st-key-home_del_"] button * {
        color: #f8f8f8 !important;
    }
    [class*="st-key-home_goto_btn_"] button {
        overflow: hidden !important;
    }
    [class*="st-key-home_goto_btn_"] button p {
        white-space: nowrap !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
        display: block !important;
        max-width: 100% !important;
    }
    /* 항목 간 여백 */
    [class*="st-key-home_goto_"] {
        margin-bottom: 2px !important;
    }
    /* 항상 가로 배치 유지 (모바일 스택킹 방지) */
    [class*="st-key-home_goto_"] .stHorizontalBlock {
        flex-wrap: nowrap !important;
    }
    /* 메인 버튼 컬럼: 남은 공간 차지, 넘침 숨김 */
    [class*="st-key-home_goto_"] .stHorizontalBlock > div:first-child {
        flex: 1 1 auto !important;
        min-width: 0 !important;
        max-width: none !important;
    }
    /* 컬럼 간격 축소 */
    [class*="st-key-home_goto_"] .stHorizontalBlock {
        gap: 4px !important;
    }
    /* 수정·삭제 버튼 컬럼: 동일 고정 폭 */
    [class*="st-key-home_goto_"] .stHorizontalBlock > div:nth-child(2),
    [class*="st-key-home_goto_"] .stHorizontalBlock > div:nth-child(3) {
        flex: 0 0 72px !important;
        min-width: 72px !important;
        max-width: 72px !important;
    }
    </style>
    """, unsafe_allow_html=True)

    # ── 카메라 권한 사전 허용 (세션당 1회 자동 트리거, UI 안내 배너 없음) ──
    # 로그인 후 홈 첫 진입 시 안내 메시지 없이 1초 후 자동으로 getUserMedia
    # 호출 → 브라우저 권한 다이얼로그. 이후 사진등록 페이지에서는 추가
    # 다이얼로그 없이 즉시 카메라 활성화 (HTTPS·localhost 환경에서 권한 영구 저장).
    if not st.session_state.get("camera_perm_requested", False):
        import streamlit.components.v1 as _components  # deprecation 처리 별도 task
        _components.html(
            """
            <script>
            setTimeout(async () => {
              const TAG = "[camera-perm]";
              try {
                // 1) Permissions API로 현재 상태 우선 확인
                let state = "prompt";
                try {
                  const res = await navigator.permissions.query({name: 'camera'});
                  state = res.state;
                  console.log(TAG, "current state:", state);
                } catch (_e) {
                  console.log(TAG, "Permissions API unsupported, fallback to getUserMedia");
                }
                // 2) granted가 아니면 명시적으로 요청 — 후면 카메라 힌트 포함
                if (state !== "granted") {
                  const stream = await navigator.mediaDevices.getUserMedia({
                    video: { facingMode: { ideal: 'environment' } }
                  });
                  stream.getTracks().forEach(t => t.stop());  // 즉시 닫음
                  console.log(TAG, "permission granted via getUserMedia (rear hint)");
                } else {
                  console.log(TAG, "already granted, no prompt needed");
                }
              } catch (e) {
                console.warn(TAG, "denied or unavailable:", e && e.name, e && e.message);
              }
            }, 1000);  // 1초 후 — 안내 메시지가 렌더링되어 보일 시간 확보
            </script>
            """,
            height=0,
        )
        st.session_state["camera_perm_requested"] = True

    inbox = approvals_inbox(con, role, st.session_state.get("IS_ADMIN", False))
    st.markdown(f"""
    <div class="card">
      <h3 style="margin:0 0 1px 0;">🏠 홈</h3>
      <p style="margin:0 0 8px 0; color:var(--text-secondary); font-size:13px;">신청 → 계획 확정(공사/안전) → 점검/등록 → SNS 공유</p>
      <p style="margin:0; font-size:13px;"><strong>내 확정 대기 :</strong> {len(inbox)}건</p>
    </div>
    """, unsafe_allow_html=True)

    # 신규 신청 버튼
    if st.button("＋ 신규 신청", key="home_new_req", type="primary", use_container_width=False):
        st.session_state["ACTIVE_PAGE"] = "신청"
        st.rerun()

    st.markdown("<div style='margin-top:16px'></div>", unsafe_allow_html=True)

    # 전체 요청 목록 (진행 중인 건 우선)
    all_reqs = req_list(con, limit=100)
    today = date.today().isoformat()
    active_reqs = [r for r in all_reqs if r.get("status") not in ("DONE",) and (not r.get("date") or r.get("date") >= today)]
    active_reqs = sorted(active_reqs, key=lambda r: r.get("created_at", ""), reverse=True)

    STATUS_LABEL = {
        "PENDING_APPROVAL": ("대기중", "status-pending"),
        "APPROVED":         ("확정됨", "status-approved"),
        "REJECTED":         ("반려됨", "status-rejected"),
        "EXECUTING":        ("실행중", "status-executing"),
        "DONE":             ("완료",   "status-done"),
    }
    PAGE_FOR_STATUS = {
        "PENDING_APPROVAL": "승인",
        "APPROVED":         "사진등록",
        "REJECTED":         "승인",
        "EXECUTING":        "사진등록",
        "DONE":             "산출물",
    }

    if not active_reqs:
        st.markdown('<div class="card" style="text-align:center;color:var(--text-muted);font-size:13px;">진행 중인 요청이 없습니다.</div>', unsafe_allow_html=True)
        return

    for r in active_reqs[:20]:
        rid = r["id"]
        kind = "반입" if r.get("kind") == KIND_IN else "반출"
        status = r.get("status", "PENDING_APPROVAL")
        slabel, _ = STATUS_LABEL.get(status, (status, "status-pending"))
        status_icon = {
            "PENDING_APPROVAL": "✍️",
            "APPROVED":         "🚛",
            "EXECUTING":        "📸",
            "DONE":             "📦",
            "REJECTED":         "❌",
        }.get(status, "📋")
        title = f"{kind} · {r.get('company_name','')} · {r.get('item_name','')}"
        sub = f"{r.get('date','')} {r.get('time_from','')}~{r.get('time_to','')} | {r.get('driver_name','')}"
        target_page = PAGE_FOR_STATUS.get(status, "승인")
        _zone = r.get('booking_zone') or ''
        _gate = r.get('gate') or ''
        _gate_txt = f" · {_gate}" if _gate and _gate != '선택' else ''
        _zone_txt = f"[{_zone}] " if _zone else ''
        label = f"{status_icon} {_zone_txt}{title} · {r.get('date','')} {r.get('time_from','')}~{r.get('time_to','')}{_gate_txt} | {slabel}"

        can_delete = is_admin or (
            role == "협력사" and r.get("requester_name") == user_name
        )
        can_edit = is_admin or (
            role == "협력사" and r.get("requester_name") == user_name
            and status == "PENDING_APPROVAL"
        )

        with st.container(key=f"home_goto_{rid}"):
            if can_edit and can_delete:
                gcol, ecol, dcol = st.columns([7, 1.5, 1.5])
            elif can_edit or can_delete:
                gcol, acol = st.columns([8, 2])
                ecol = acol if can_edit else None
                dcol = acol if can_delete else None
            else:
                gcol = st.columns(1)[0]
                ecol = dcol = None
            with gcol:
                if st.button(label, key=f"home_goto_btn_{rid}", use_container_width=True):
                    st.session_state["ACTIVE_PAGE"] = target_page
                    st.session_state["SELECTED_REQ_ID"] = rid
                    st.rerun()
            if ecol and can_edit:
                with ecol:
                    if st.button("수정", key=f"home_edit_{rid}", use_container_width=True):
                        from modules.schedule.crud import schedule_by_req_id
                        from datetime import date as _date
                        sched = schedule_by_req_id(con, rid)
                        if sched:
                            sched_date = sched.get("schedule_date", str(_date.today()))
                            import datetime
                            st.session_state["sched_current_date"] = datetime.date.fromisoformat(sched_date)
                            if is_admin:
                                st.session_state["admin_sel_sched_ids"]  = [sched["id"]]
                                st.session_state["admin_sel_sched_list"] = [sched]
                                st.session_state["admin_sel_sched_kind"] = sched.get("kind", "IN")
                            else:
                                st.session_state["user_sel_sched_list"] = [sched]
                        st.session_state["sched_sel_in_slots"]   = []
                        st.session_state["sched_sel_out_slots"]  = []
                        st.session_state["sched_edit_from_home"] = True
                        st.session_state["ACTIVE_PAGE"] = "신청"
                        st.rerun()
            if dcol and can_delete:
                with dcol:
                    if st.button("삭제", key=f"home_del_{rid}", use_container_width=True):
                        req_delete(con, rid)
                        st.toast("삭제되었습니다.", icon="🗑️")
                        st.rerun()


def _inject_eruda():
    """Mobile in-app DevTools (Eruda) — only when DEBUG_TIMING=true.

    Eruda adds a floating gear button to the page that opens a DevTools-like
    panel (Console / Elements / Network / ...). On mobile devices where F12 is
    unavailable, this is the easiest way to read `[camera-perm]` /
    `[camera-toggle]` and similar console logs.

    Injected via a one-shot script in the parent window (not in the iframe
    sandbox) so it can inspect the real Streamlit app DOM.
    """
    if str(st.secrets.get("DEBUG_TIMING", "false")).lower() not in ("true", "1", "yes"):
        return
    if st.session_state.get("__eruda_injected"):
        return
    st.session_state["__eruda_injected"] = True
    import streamlit.components.v1 as _components  # deprecation handled in separate task
    _components.html(
        """
        <script>
        (function() {
          try {
            const pwin = window.parent;
            if (pwin.__eruda_loaded) return;
            pwin.__eruda_loaded = true;
            const s = pwin.document.createElement('script');
            s.src = 'https://cdn.jsdelivr.net/npm/eruda';
            s.onload = function() {
              try {
                pwin.eruda.init();
                // 초기 위치를 좌하단으로 (기본은 우하단)
                const setPos = () => {
                  try {
                    const w = pwin.innerWidth, h = pwin.innerHeight;
                    pwin.eruda.position({ x: 10, y: h - 60 });
                  } catch (_e) { /* 일부 버전에서 position 미지원 */ }
                };
                setPos();
                pwin.addEventListener('resize', setPos);
                console.log('[eruda] mobile DevTools ready — tap the gear button (bottom-left)');
              } catch (e) {
                console.warn('[eruda] init failed:', e);
              }
            };
            s.onerror = function() {
              console.warn('[eruda] failed to load script (CDN blocked?)');
            };
            pwin.document.head.appendChild(s);
          } catch (e) {
            console.warn('[eruda] inject failed:', e);
          }
        })();
        </script>
        """,
        height=0,
    )


def _inject_camera_default_environment():
    """Force getUserMedia facingMode to 'environment' (rear camera).

    Two-pronged strategy applied once per session:

      1) Monkey-patch ``window.parent.navigator.mediaDevices.getUserMedia`` so
         that EVERY video request — regardless of what facingMode the caller
         specified — is rewritten to use ``{ideal: 'environment'}``. ``ideal``
         (not ``exact``) lets the browser fall back to the front camera on
         devices without a rear one — no NotFoundError.

      2) Pre-warm: if the camera permission is already granted, call
         ``getUserMedia({video: {facingMode: {ideal: 'environment'}}})`` once
         and immediately stop the stream. Browsers tend to remember the
         last-used camera for the origin, so this nudges st.camera_input
         toward rear even on devices where (1) somehow doesn't reach its
         execution context (defensive).

    Skipped when permission state is not 'granted' to avoid stealing the
    permission dialog from the page_home pre-request flow.
    """
    if st.session_state.get("__cam_default_set"):
        return
    st.session_state["__cam_default_set"] = True
    import streamlit.components.v1 as _components  # deprecation handled in separate task
    _components.html(
        """
        <script>
        (async function() {
          const TAG = "[cam-default]";
          try {
            const pwin = window.parent;
            if (pwin.__camDefaulted) return;
            pwin.__camDefaulted = true;
            const md = pwin.navigator && pwin.navigator.mediaDevices;
            if (!md || !md.getUserMedia) {
              console.warn(TAG, "mediaDevices unavailable");
              return;
            }

            // 1) Monkey-patch — always force 'environment' (rear)
            if (!md.__origGUM) md.__origGUM = md.getUserMedia.bind(md);
            md.getUserMedia = function(constraints) {
              try {
                constraints = constraints || {};
                if (constraints.video === undefined) constraints.video = true;
                if (constraints.video === true) constraints.video = {};
                if (typeof constraints.video === 'object') {
                  // Always force rear. 'ideal' (not 'exact') keeps single-camera
                  // devices working — browser falls back to front automatically.
                  constraints.video.facingMode = { ideal: 'environment' };
                }
                console.log(TAG, "gUM →", JSON.stringify(constraints));
              } catch (e) { console.warn(TAG, "patch err:", e); }
              return md.__origGUM(constraints);
            };
            console.log(TAG, "monkey-patched getUserMedia (force environment)");

            // 2) Pre-warm — only if permission is already granted (avoid
            //    competing with the page_home permission pre-request)
            let state = "unknown";
            try {
              const res = await pwin.navigator.permissions.query({name: 'camera'});
              state = res.state;
            } catch (_e) { /* Permissions API may not support 'camera' on some browsers */ }
            if (state === "granted") {
              try {
                const stream = await pwin.navigator.mediaDevices.getUserMedia({
                  video: { facingMode: { ideal: 'environment' } }
                });
                stream.getTracks().forEach(t => t.stop());
                console.log(TAG, "pre-warmed rear camera");
              } catch (e) {
                console.warn(TAG, "pre-warm failed:",
                             (e && (e.name + ": " + e.message)) || e);
              }
            } else {
              console.log(TAG, "skipping pre-warm (perm state:", state, ")");
            }
          } catch (e) {
            console.warn(TAG, "inject failed:", e);
          }
        })();
        </script>
        """,
        height=0,
    )


def main():
    """Main application entry point."""
    # ── DEBUG_TIMING: reset per-rerun timers (no-op when disabled) ──
    clear_timings()

    # ── PWA: 송도2-INO 명칭/아이콘으로 manifest 덮어쓰기 (세션당 1회) ──
    inject_pwa()

    # ── DEBUG_TIMING: inject Eruda mobile DevTools (no-op when disabled) ──
    _inject_eruda()

    # ── Camera default: prefer rear (environment) facing for st.camera_input ──
    _inject_camera_default_environment()

    # ── DB init (Supabase: schema is managed via Supabase CLI / SQL migrations) ──
    con = con_open()

    # ── CSS ──
    inject_css()

    # ── Session defaults ──
    if "AUTH_OK" not in st.session_state:
        st.session_state["AUTH_OK"] = False
    if "BASE_DIR" not in st.session_state:
        st.session_state["BASE_DIR"] = "MaterialToolShared"
    if "ACTIVE_PAGE" not in st.session_state:
        st.session_state["ACTIVE_PAGE"] = "홈"

    # ── Step 1: Project selection (단일 프로젝트면 자동 선택) ──
    if not session_has_project():
        from db.models import project_list
        projects = project_list(con)
        if len(projects) == 1:
            st.session_state["PROJECT_ID"]   = projects[0]["id"]
            st.session_state["PROJECT_NAME"] = projects[0]["name"]
        else:
            page_project_select(con)
            render_panel()
            return

    # ── Step 2: Authentication ──
    if not session_is_authed():
        page_login(con)
        render_panel()
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

    # ── DEBUG_TIMING: show summary in sidebar (no-op when disabled) ──
    render_panel()


if __name__ == "__main__":
    main()
