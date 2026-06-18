"""터미널 보관·반출 관리 페이지."""
from datetime import date as _date

import streamlit as st
from supabase import Client

from modules.terminal.crud import (
    terminal_max_days, terminal_occupied, terminal_history, terminal_release,
)
from shared.storage_plan import terminals_b1, terminals_b2, occupancy_on, floor_image


def _occ_grid_html(terminals, occ, max_days: int = 0) -> str:
    from datetime import date as _d, timedelta
    today = _d.today()
    cells = []
    for t in terminals:
        o = occ.get(t)
        if o:
            item_txt = (o.get('item') or '')[:9]
            end_txt = ""
            overdue = False
            if max_days and o.get('start'):
                try:
                    start_d = _d.fromisoformat(o['start'][:10])
                    end_d   = start_d + timedelta(days=max_days)
                    overdue = today > end_d
                    end_txt = f"<div style='font-size:10px;margin-top:2px;'>~{end_d.month}/{end_d.day}</div>"
                except Exception:
                    pass
            if overdue:
                bg, border, num_clr, lbl_clr = "#fef2f2", "2px solid #ef4444", "#b91c1c", "#dc2626"
            else:
                bg, border, num_clr, lbl_clr = "#fefce8", "2px solid #fcd34d", "#92400e", "#a16207"
            inner = (
                f"<div style='font-size:11px;font-weight:700;color:{num_clr};'>{t}</div>"
                f"<div style='font-size:10px;color:{lbl_clr};margin-top:1px;word-break:break-all;'>{item_txt}</div>"
                f"<div style='font-size:10px;color:{lbl_clr};'>{end_txt}</div>"
            )
        else:
            bg, border, num_clr = "#f0fdf4", "1.5px solid #86efac", "#15803d"
            inner = (
                f"<div style='font-size:11px;font-weight:700;color:{num_clr};'>{t}</div>"
                f"<div style='font-size:10px;color:#22c55e;margin-top:2px;'>빈곳</div>"
            )
        cells.append(
            f"<div style='width:68px;min-height:58px;background:{bg};border:{border};"
            f"border-radius:8px;padding:6px 4px;text-align:center;line-height:1.3;"
            f"box-shadow:0 1px 3px rgba(0,0,0,0.08);'>{inner}</div>"
        )
    legend = (
        "<div style='display:flex;gap:12px;align-items:center;margin-bottom:8px;font-size:11px;color:#64748b;'>"
        "<span style='display:inline-flex;align-items:center;gap:4px;'>"
        "<span style='width:12px;height:12px;background:#fef2f2;border:2px solid #ef4444;border-radius:3px;display:inline-block;'></span>기한초과</span>"
        "<span style='display:inline-flex;align-items:center;gap:4px;'>"
        "<span style='width:12px;height:12px;background:#fefce8;border:2px solid #fcd34d;border-radius:3px;display:inline-block;'></span>점유중</span>"
        "<span style='display:inline-flex;align-items:center;gap:4px;'>"
        "<span style='width:12px;height:12px;background:#f0fdf4;border:1.5px solid #86efac;border-radius:3px;display:inline-block;'></span>빈곳</span>"
        "</div>"
    )
    grid = "<div style='display:flex;flex-wrap:wrap;gap:6px;margin-bottom:8px;'>" + "".join(cells) + "</div>"
    return legend + grid


def _render_floor(rows, label, max_days, today, user_id, con):
    st.markdown(
        f'<div style="font-weight:700;font-size:13px;color:#1e3a8a;'
        f'padding:6px 0 4px 0;border-bottom:2px solid #1e3a8a;margin-bottom:14px;">'
        f'{label} ({len(rows)}건)</div>',
        unsafe_allow_html=True,
    )
    if not rows:
        st.markdown(
            '<div style="font-size:12px;color:#94a3b8;padding:4px 0 10px 0;">보관 자재 없음</div>',
            unsafe_allow_html=True,
        )
        return
    for r in rows:
        rid   = r["id"]
        term  = r["terminal"]
        co    = r.get("company_name", "")
        item  = r.get("item_name", "")
        d_str = (r.get("date") or "")[:10]
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
                    f'<div style="padding:5px 0;">'
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
                    st.toast(f"✅ {term} 반출 완료")
                    st.rerun()


def page_terminal(con: Client) -> None:
    role       = st.session_state.get("USER_ROLE", "")
    is_admin   = st.session_state.get("IS_ADMIN", False)
    company    = st.session_state.get("USER_COMPANY", "")
    user_id    = st.session_state.get("USER_ID", "")
    project_id = st.session_state.get("PROJECT_ID", "")

    filter_co = None if (is_admin or role != "협력사") else company
    max_days  = terminal_max_days(con, project_id)

    st.markdown(
        '<div class="card"><h3 style="margin:0 0 4px 0;">📦 터미널 보관·반출 관리</h3>'
        f'<p style="margin:0;font-size:12px;color:var(--text-muted);">최대 보관 기준: {max_days}일</p></div>',
        unsafe_allow_html=True,
    )

    # ── 도면 익스팬더 ────────────────────────────────────────────────────────
    with st.expander("🗺 터미널 도면 (B1F · B2F)"):
        _occ = occupancy_on(con, project_id, _date.today().isoformat())
        st.caption(f"📅 오늘({_date.today().isoformat()}) 기준 점유 현황 (빨강=점유, 초록=빈곳)")

        floor_sel = st.radio("층 선택", ["B1F", "B2F"], horizontal=True, key="term_floor_sel")
        if floor_sel == "B1F":
            img = floor_image("b1")
            if img:
                st.image(img, use_container_width=True)
            st.markdown(_occ_grid_html(terminals_b1(), _occ, max_days), unsafe_allow_html=True)
        else:
            img = floor_image("b2")
            if img:
                st.image(img, use_container_width=True)
            st.markdown(_occ_grid_html(terminals_b2(), _occ, max_days), unsafe_allow_html=True)

    tab1, tab2 = st.tabs(["보관 현황", "반출 이력"])

    # ── 보관 현황 ────────────────────────────────────────────────────────────
    with tab1:
        occupied = terminal_occupied(con, project_id, filter_co)
        today    = _date.today()
        b1 = [r for r in occupied if r["terminal"].startswith("B1-")]
        b2 = [r for r in occupied if r["terminal"].startswith("B2-")]

        if not occupied:
            st.info("현재 보관 중인 자재가 없습니다.")
        else:
            _render_floor(b1, "B1F", max_days, today, user_id, con)
            st.markdown("<div style='margin-top:16px'></div>", unsafe_allow_html=True)
            _render_floor(b2, "B2F", max_days, today, user_id, con)

    # ── 반출 이력 ────────────────────────────────────────────────────────────
    with tab2:
        history = terminal_history(con, project_id, filter_co)
        if not history:
            st.info("반출 이력이 없습니다.")
        else:
            b1h = [r for r in history if r["terminal"].startswith("B1-")]
            b2h = [r for r in history if r["terminal"].startswith("B2-")]

            def _render_history(rows, label):
                st.markdown(
                    f'<div style="font-weight:700;font-size:13px;color:#1e3a8a;'
                    f'padding:6px 0 4px 0;border-bottom:2px solid #1e3a8a;margin-bottom:14px;">'
                    f'{label}</div>',
                    unsafe_allow_html=True,
                )
                if not rows:
                    st.markdown(
                        '<div style="font-size:12px;color:#94a3b8;padding:4px 0 10px 0;">이력 없음</div>',
                        unsafe_allow_html=True,
                    )
                    return
                for r in rows:
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

            _render_history(b1h, "B1F")
            st.markdown("<div style='margin-top:16px'></div>", unsafe_allow_html=True)
            _render_history(b2h, "B2F")
