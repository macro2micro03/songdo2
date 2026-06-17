"""Hero header rendering."""
import streamlit as st
from datetime import date
from supabase import Client

from config import APP_VERSION, DEFAULT_SITE_NAME
from db.models import settings_get
from shared.timing import measure


@measure("core.ui_header")
def ui_header(con: Client):
    """Render hero header with KPI stats."""
    # 프로젝트명 우선, 없으면 settings의 site_name 사용
    site_name = st.session_state.get("PROJECT_NAME") or settings_get(con, "site_name", DEFAULT_SITE_NAME)
    user_name = st.session_state.get("USER_NAME", "")
    user_role = st.session_state.get("USER_ROLE", "")
    is_admin = st.session_state.get("IS_ADMIN", False)
    project_id = st.session_state.get("PROJECT_ID", "")
    today = date.today().isoformat()

    # 한글 폰트 등록 진단 — 관리자에게만 노출
    if is_admin:
        try:
            from modules.outputs.pdf import KOREAN_FONT_REGISTERED, KOREAN_FONT_DIAG
            if not KOREAN_FONT_REGISTERED:
                with st.expander("⚠️ 한글 폰트 미등록 — PDF 산출물이 □로 깨질 수 있습니다", expanded=False):
                    st.json(KOREAN_FONT_DIAG)
                    st.caption("modules/outputs/fonts/NanumGothic.ttf 존재 여부 / Streamlit Cloud 재배포 확인")
        except Exception:
            pass
    res = (con.table("requests").select("status,vehicle_count")
           .eq("project_id", project_id).eq("date", today).execute())
    rows = res.data or []
    total = len(rows)
    pending = approved = done = 0
    total_v = pending_v = approved_v = done_v = 0
    for r in rows:
        s = r.get("status", "")
        v = r.get("vehicle_count") or 0
        try:
            v = int(v)
        except (TypeError, ValueError):
            v = 0
        total_v += v
        if s == "PENDING_APPROVAL":
            pending += 1
            pending_v += v
        elif s in ("APPROVED", "EXECUTING"):
            approved += 1
            approved_v += v
        elif s == "DONE":
            done += 1
            done_v += v
    st.markdown(f"""
    <div class="hero">
      <div class="hero-content">
        <div class="title" style="display:flex;align-items:center;gap:8px;justify-content:center;">
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 72" width="32" height="32">
            <rect x="62" y="18" width="76" height="34" rx="3" fill="#1e3a8a"/>
            <rect x="118" y="24" width="20" height="22" rx="3" fill="#2563eb"/>
            <rect x="121" y="27" width="14" height="11" rx="2" fill="#bfdbfe"/>
            <rect x="64" y="20" width="52" height="28" rx="2" fill="#3b82f6"/>
            <rect x="67" y="24" width="14" height="12" rx="1" fill="#fbbf24"/>
            <rect x="83" y="24" width="14" height="12" rx="1" fill="#f59e0b"/>
            <rect x="99" y="24" width="14" height="12" rx="1" fill="#fbbf24"/>
            <circle cx="82" cy="54" r="8" fill="#1e293b"/>
            <circle cx="82" cy="54" r="4" fill="#94a3b8"/>
            <circle cx="126" cy="54" r="8" fill="#1e293b"/>
            <circle cx="126" cy="54" r="4" fill="#94a3b8"/>
            <line x1="0" y1="62" x2="160" y2="62" stroke="#cbd5e1" stroke-width="1.5"/>
            <rect x="8" y="30" width="36" height="24" rx="3" fill="#f59e0b"/>
            <rect x="28" y="22" width="16" height="16" rx="2" fill="#fbbf24"/>
            <rect x="30" y="24" width="12" height="9" rx="1" fill="#bfdbfe"/>
            <rect x="6" y="14" width="4" height="40" rx="1" fill="#d97706"/>
            <rect x="2" y="30" width="8" height="3" rx="1" fill="#92400e"/>
            <rect x="2" y="36" width="8" height="3" rx="1" fill="#92400e"/>
            <rect x="2" y="18" width="14" height="12" rx="1" fill="#fbbf24" stroke="#d97706" stroke-width="1"/>
            <circle cx="18" cy="55" r="7" fill="#1e293b"/>
            <circle cx="18" cy="55" r="3.5" fill="#94a3b8"/>
            <circle cx="38" cy="55" r="7" fill="#1e293b"/>
            <circle cx="38" cy="55" r="3.5" fill="#94a3b8"/>
            <path d="M50 40 L60 40" stroke="#ef4444" stroke-width="2.5" stroke-dasharray="3,2" marker-end="url(#arr)"/>
            <defs>
              <marker id="arr" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
                <path d="M0,0 L0,6 L6,3 Z" fill="#ef4444"/>
              </marker>
            </defs>
          </svg>
          <span>{site_name}</span>
        </div>
        <div class="sub">{APP_VERSION} · 현장 자재 반출입 관리 · 👤 {user_name} ({user_role}){"&nbsp;&nbsp;🔐 관리자" if is_admin else ""}</div>
        <div class="kpi" style="margin-top:8px;">
          <div class="box" style="background:#f1f5f9;border:1px solid #94a3b8;display:flex;flex-direction:column;align-items:center;justify-content:center;">
            <div style="display:flex;align-items:center;gap:4px;">
              <span style="font-size:1.3em;font-weight:700;color:#334155;">{total}</span>
              <span style="color:#cbd5e1;font-size:1em;line-height:1;">|</span>
              <span style="font-size:0.85em;font-weight:400;color:#94a3b8;">{total_v}대</span>
            </div>
            <div style="font-size:11px;color:#475569;margin-top:2px;">전체 요청</div>
          </div>
          <div class="box" style="background:#f1f5f9;border:1px solid #94a3b8;display:flex;flex-direction:column;align-items:center;justify-content:center;">
            <div style="display:flex;align-items:center;gap:4px;">
              <span style="font-size:1.3em;font-weight:700;color:#d97706;">{pending}</span>
              <span style="color:#cbd5e1;font-size:1em;line-height:1;">|</span>
              <span style="font-size:0.85em;font-weight:400;color:#94a3b8;">{pending_v}대</span>
            </div>
            <div style="font-size:11px;color:#475569;margin-top:2px;">대기중</div>
          </div>
          <div class="box" style="background:#f1f5f9;border:1px solid #94a3b8;display:flex;flex-direction:column;align-items:center;justify-content:center;">
            <div style="display:flex;align-items:center;gap:4px;">
              <span style="font-size:1.3em;font-weight:700;color:#16a34a;">{approved}</span>
              <span style="color:#cbd5e1;font-size:1em;line-height:1;">|</span>
              <span style="font-size:0.85em;font-weight:400;color:#94a3b8;">{approved_v}대</span>
            </div>
            <div style="font-size:11px;color:#475569;margin-top:2px;">승인됨</div>
          </div>
          <div class="box" style="background:#f1f5f9;border:1px solid #94a3b8;display:flex;flex-direction:column;align-items:center;justify-content:center;">
            <div style="display:flex;align-items:center;gap:4px;">
              <span style="font-size:1.3em;font-weight:700;color:#2563eb;">{done}</span>
              <span style="color:#cbd5e1;font-size:1em;line-height:1;">|</span>
              <span style="font-size:0.85em;font-weight:400;color:#94a3b8;">{done_v}대</span>
            </div>
            <div style="font-size:11px;color:#475569;margin-top:2px;">완료</div>
          </div>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)
