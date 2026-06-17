"""날짜별 대시보드 — 자재 상·하차 반입/반출 현황 테이블."""
import io
from datetime import date, timedelta
import streamlit as st
from shared.timing import measure
from supabase import Client
from config import KIND_IN, KIND_OUT
from db.models import settings_get


_DASH_CSS = """
<style>
/* 날짜 네비 */
.st-key-dash_nav { margin-bottom: 16px !important; }
.st-key-dash_nav .stHorizontalBlock {
  gap: 4px !important;
  align-items: center !important;
  flex-wrap: nowrap !important;
}
/* 버튼 컬럼(◀◀ ◀ ▶ ▶▶): 고정 최소폭 */
.st-key-dash_nav .stHorizontalBlock > div:nth-child(1),
.st-key-dash_nav .stHorizontalBlock > div:nth-child(2),
.st-key-dash_nav .stHorizontalBlock > div:nth-child(4),
.st-key-dash_nav .stHorizontalBlock > div:nth-child(5) {
  flex: 0 0 40px !important;
  min-width: 40px !important;
  max-width: 40px !important;
}
/* 6번째 컬럼(오늘 버튼): 살짝 넓게 — 한글 두 글자 표시 */
.st-key-dash_nav .stHorizontalBlock > div:nth-child(6) {
  flex: 0 0 56px !important;
  min-width: 56px !important;
  max-width: 56px !important;
}
/* 날짜 박스 컬럼: 남은 공간 차지 */
.st-key-dash_nav .stHorizontalBlock > div:nth-child(3) {
  flex: 1 1 auto !important;
  min-width: 0 !important;
}
.st-key-dash_nav button {
  height: 38px !important;
  min-height: 38px !important;
  max-height: 38px !important;
  padding: 0 !important;
  font-size: 13px !important;
  display: flex !important;
  align-items: center !important;
  justify-content: center !important;
}
.st-key-dash_nav button p,
.st-key-dash_nav button span {
  display: flex !important;
  align-items: center !important;
  justify-content: center !important;
  margin: 0 !important;
  line-height: 1 !important;
}
.st-key-dash_nav [data-baseweb="input"] {
  height: 38px !important;
  min-height: 38px !important;
}
.st-key-dash_nav [data-baseweb="input"] input {
  height: 38px !important;
  line-height: 38px !important;
  padding-top: 0 !important;
  padding-bottom: 0 !important;
  text-align: center !important;
}

/* 대시보드 래퍼 */
div.dash-wrap {
  width: 100% !important;
  overflow-x: scroll !important;
  -webkit-overflow-scrolling: touch !important;
  cursor: grab !important;
}
div.dash-wrap:active { cursor: grabbing !important; }

/* 가로 스크롤바를 굵고 잡기 쉽게 */
div.dash-wrap::-webkit-scrollbar { height: 14px !important; }
div.dash-wrap::-webkit-scrollbar-track { background: #cbd5e1 !important; border-radius: 7px !important; }
div.dash-wrap::-webkit-scrollbar-thumb { background: #64748b !important; border-radius: 7px !important; border: 2px solid #cbd5e1 !important; }
div.dash-wrap::-webkit-scrollbar-thumb:hover { background: #334155 !important; }

/* 타이틀 박스 */
.dash-title-box {
  border: 2px solid #1e3a8a;
  border-radius: 4px;
  text-align: center;
  padding: 16px 8px 14px 8px;
  margin-bottom: 12px;
  width: 100%;
  box-sizing: border-box;
}
.dash-title-box h2 {
  font-size: clamp(20px, 4vw, 32px);
  font-weight: 900;
  color: #0f172a;
  margin: 0;
  letter-spacing: -0.5px;
}

/* 사이트·날짜 헤더 */
.dash-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
  font-size: 13px;
  color: #1e3a8a;
  font-weight: 600;
}

/* 테이블 */
.dash-table {
  width: 100%;
  border-collapse: collapse;
  font-size: clamp(11px, 1.8vw, 13px);
  min-width: 860px;
}
.dash-table th {
  background: #1e3a8a;
  color: #ffffff;
  padding: 8px 6px;
  text-align: center;
  border: 1px solid #1e40af;
  font-weight: 700;
  white-space: nowrap;
  vertical-align: middle;
}
.dash-table th.th-sub {
  background: #2563eb;
  font-size: 11px;
  padding: 5px 4px;
}
.dash-table td {
  padding: 7px 6px;
  border: 1px solid #cbd5e1;
  text-align: center !important;
  vertical-align: middle !important;
  color: #0f172a;
  word-break: keep-all;
  cursor: help;
}
.dash-table td:hover {
  background: #dbeafe !important;
}
.tooltip-content {
  position: absolute;
  bottom: 110%;
  left: 50%;
  transform: translateX(-50%);
  background: #0f172a;
  color: #ffffff;
  padding: 6px 10px;
  border-radius: 4px;
  font-size: 11px;
  white-space: nowrap;
  z-index: 9999;
  box-shadow: 0 2px 8px rgba(0,0,0,0.2);
  pointer-events: none;
  opacity: 0;
  transition: opacity 0.2s;
}
.dash-table td:hover .tooltip-content {
  opacity: 1;
}
.dash-table tr:nth-child(even) td { background: #f8fafc; }
.dash-table tr:nth-child(odd)  td { background: #ffffff; }
.dash-table tr:hover td { background: #eff6ff !important; }

/* 반입/반출 배지 */
.kind-in  { color: #1d4ed8; font-weight: 700; }
.kind-out { color: #b91c1c; font-weight: 700; }

/* 합계 행 */
.dash-table tr.total-row td {
  background: #e0e7ff !important;
  font-weight: 700;
  color: #1e3a8a;
}

/* 다운로드 버튼 */
[data-testid="stDownloadButton"] button {
  white-space: nowrap !important;
  background-color: #2563eb !important;
  border-color: #2563eb !important;
  color: #ffffff !important;
  display: flex !important;
  align-items: center !important;
  justify-content: center !important;
}
[data-testid="stDownloadButton"] button:hover {
  background-color: #1d4ed8 !important;
  border-color: #1d4ed8 !important;
}
[data-testid="stDownloadButton"] button p,
[data-testid="stDownloadButton"] button span {
  white-space: nowrap !important;
  color: #ffffff !important;
  margin: 0 !important;
  line-height: 1 !important;
}

/* 모바일: 모바일 전용 영역 숨김, 테이블 표시 (가로 스크롤 가능) */
.dash-mobile-only { display: none; }
</style>
"""


def _build_excel(reqs: list, site_name: str, date_label: str, terminal_zones: set = None) -> bytes:
    """요청 목록을 엑셀 파일로 변환하여 bytes 반환."""
    if terminal_zones is None:
        terminal_zones = set()
    from openpyxl import Workbook
    from openpyxl.styles import (
        Font, PatternFill, Alignment, Border, Side, GradientFill
    )

    wb = Workbook()
    ws = wb.active
    ws.title = "반입반출현황"

    # ── 스타일 정의 ───────────────────────────────────────────────────────
    thin = Side(style="thin", color="CBD5E1")
    thick = Side(style="medium", color="1E3A8A")
    border_all  = Border(left=thin, right=thin, top=thin, bottom=thin)
    border_thick = Border(left=thick, right=thick, top=thick, bottom=thick)

    hdr_fill   = PatternFill("solid", fgColor="1E3A8A")
    sub_fill   = PatternFill("solid", fgColor="2563EB")
    total_fill = PatternFill("solid", fgColor="E0E7FF")
    even_fill  = PatternFill("solid", fgColor="F8FAFC")

    hdr_font   = Font(name="맑은 고딕", bold=True, color="FFFFFF", size=10)
    body_font  = Font(name="맑은 고딕", size=10)
    total_font = Font(name="맑은 고딕", bold=True, color="1E3A8A", size=10)
    title_font = Font(name="맑은 고딕", bold=True, size=16)
    meta_font  = Font(name="맑은 고딕", bold=True, size=10, color="1E3A8A")

    center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    left   = Alignment(horizontal="left",   vertical="center", wrap_text=True)

    # ── 행 1: 제목 ────────────────────────────────────────────────────────
    ws.merge_cells("A1:L1")
    ws["A1"].value = "자재 상·하차 반입/반출 현황"
    ws["A1"].font  = title_font
    ws["A1"].alignment = center
    ws["A1"].border = border_thick
    ws.row_dimensions[1].height = 44

    # ── 행 2: 현장명 / 날짜 ───────────────────────────────────────────────
    ws.merge_cells("A2:F2")
    ws["A2"].value = f"□ {site_name}"
    ws["A2"].font  = meta_font
    ws["A2"].alignment = left
    ws.merge_cells("G2:L2")
    ws["G2"].value = date_label
    ws["G2"].font  = meta_font
    ws["G2"].alignment = Alignment(horizontal="right", vertical="center")
    ws.row_dimensions[2].height = 18

    # ── 행 3: 헤더 (단일행) ───────────────────────────────────────────────
    for col_letter, label in [
        ("A","No"), ("B","Zone"), ("C","터미널"), ("D","업체명"), ("E","자재종류"),
        ("F","수량"), ("G","반입·반출 차량"), ("H","상·하차 방식"),
        ("I","시간"), ("J","작업지휘자"), ("K","유도원"), ("L","담당자"),
    ]:
        ws.merge_cells(f"{col_letter}3:{col_letter}4")
        cell = ws[f"{col_letter}3"]
        cell.value = label
        cell.font  = hdr_font
        cell.fill  = hdr_fill
        cell.alignment = center
        cell.border = border_all

    ws.row_dimensions[3].height = 22
    ws.row_dimensions[4].height = 16

    # ── 데이터 행 ─────────────────────────────────────────────────────────
    dow_map = {0:"월요일", 1:"화요일", 2:"수요일", 3:"목요일",
               4:"금요일", 5:"토요일", 6:"일요일"}
    total_cnt = 0
    for i, r in enumerate(reqs, 1):
        row_num = i + 4
        kind    = r.get("kind", KIND_IN)
        kind_lbl = "반입" if kind == KIND_IN else "반출"
        company  = r.get("company_name", "")
        item     = r.get("item_name", "")
        vcnt_raw = r.get("vehicle_count", "")
        vcnt     = f"{vcnt_raw}대" if vcnt_raw else ""
        vton     = r.get("vehicle_ton", "")
        loading  = r.get("loading_method", "")
        gate_raw   = r.get("gate", "")
        gate_parts = gate_raw.split("|", 1) if "|" in gate_raw else [gate_raw, ""]
        gate_zone  = gate_parts[0].strip()
        gate_place = gate_parts[1].strip() if len(gate_parts) > 1 else ""
        t_from = r.get("time_from", "")
        sup    = r.get("worker_supervisor", "")
        guide  = r.get("worker_guide", "")
        mgr    = r.get("worker_manager", "")
        vcnt_int = int(vcnt_raw) if str(vcnt_raw).isdigit() else 0
        total_cnt += vcnt_int

        zone_xl     = r.get("booking_zone", "")
        gate_xl_raw = r.get("gate", "")
        gate_xl_raw = "" if gate_xl_raw == "선택" else gate_xl_raw
        gate_xl     = gate_xl_raw if zone_xl in terminal_zones else "N/A"
        fill = even_fill if i % 2 == 0 else PatternFill("solid", fgColor="FFFFFF")
        values = [i, zone_xl, gate_xl, company, item, vcnt, f"{kind_lbl} / {vton}", loading,
                  t_from, sup, guide, mgr]
        for col_idx, val in enumerate(values, 1):
            cell = ws.cell(row=row_num, column=col_idx, value=val)
            cell.font   = body_font
            cell.fill   = fill
            cell.border = border_all
            cell.alignment = center
        ws.row_dimensions[row_num].height = 18

    # ── 합계 행 ───────────────────────────────────────────────────────────
    total_row = len(reqs) + 5
    ws.merge_cells(f"A{total_row}:D{total_row}")
    ws[f"A{total_row}"].value = "합 계"
    ws[f"A{total_row}"].font  = total_font
    ws[f"A{total_row}"].fill  = total_fill
    ws[f"A{total_row}"].alignment = Alignment(horizontal="right", vertical="center")
    ws[f"A{total_row}"].border = border_all
    ws[f"E{total_row}"].value = f"{total_cnt}대"
    ws[f"E{total_row}"].font  = total_font
    ws[f"E{total_row}"].fill  = total_fill
    ws[f"E{total_row}"].alignment = center
    ws[f"E{total_row}"].border = border_all
    for col_idx in range(6, 13):
        cell = ws.cell(row=total_row, column=col_idx)
        cell.fill   = total_fill
        cell.border = border_all
    ws.row_dimensions[total_row].height = 18

    # ── 열 너비 ───────────────────────────────────────────────────────────
    from openpyxl.utils import get_column_letter
    col_widths = [5, 8, 14, 14, 7, 14, 12, 10, 8, 12, 10, 10]
    for col_idx, w in enumerate(col_widths, 1):
        ws.column_dimensions[get_column_letter(col_idx)].width = w

    # ── bytes 반환 ────────────────────────────────────────────────────────
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()


def _req_list_for_date(con: Client, project_id: str, target_date: str):
    res = (con.table("requests").select("*")
           .eq("project_id", project_id).eq("date", target_date)
           .order("booking_zone").order("time_from").order("created_at")
           .execute())
    return res.data or []


@measure("page.dashboard")


def page_dashboard(con: Client):
    st.markdown(_DASH_CSS, unsafe_allow_html=True)

    project_id = st.session_state.get("PROJECT_ID", "")
    site_name  = settings_get(con, "site_name", "현장명")

    # ── 날짜 상태 (단일 소스 — date_input의 widget state) ───────────────────
    # Streamlit 함정: st.date_input은 key가 있으면 widget state가 value보다 우선.
    # 이전 구현은 별도 'dash_date' 변수와 widget state를 병행 운영 → sync 깨짐.
    # 수정: dash_date_picker 단일 source of truth로 통일하고, nav 버튼이
    # 같은 key를 직접 갱신하도록 변경.
    if "dash_date_picker" not in st.session_state:
        st.session_state["dash_date_picker"] = date.today()
    cur_date: date = st.session_state["dash_date_picker"]
    today: date = date.today()

    # ── 날짜 네비게이션 ───────────────────────────────────────────────────
    with st.container(key="dash_nav"):
        # 6 columns: ◀◀ ◀ [date_input] ▶ ▶▶ [오늘]
        nc1, nc2, nc3, nc4, nc5, nc6 = st.columns([1, 1, 2.6, 1, 1, 1])
        with nc1:
            if st.button("◀◀", key="dash_prev_week", use_container_width=True, help="일주일 전"):
                st.session_state["dash_date_picker"] = cur_date - timedelta(days=7)
                st.rerun()
        with nc2:
            if st.button("◀", key="dash_prev_day", use_container_width=True, help="전날"):
                st.session_state["dash_date_picker"] = cur_date - timedelta(days=1)
                st.rerun()
        with nc3:
            # value= 제거: widget state(dash_date_picker)가 단독 소스.
            # 캘린더에서 직접 선택 시 자동으로 widget state 갱신 → 다음 rerun에서 cur_date 반영.
            st.date_input(
                "날짜", key="dash_date_picker",
                label_visibility="collapsed",
            )
        with nc4:
            if st.button("▶", key="dash_next_day", use_container_width=True, help="다음날"):
                st.session_state["dash_date_picker"] = cur_date + timedelta(days=1)
                st.rerun()
        with nc5:
            if st.button("▶▶", key="dash_next_week", use_container_width=True, help="일주일 후"):
                st.session_state["dash_date_picker"] = cur_date + timedelta(days=7)
                st.rerun()
        with nc6:
            is_today = (cur_date == today)
            if st.button(
                "오늘",
                key="dash_today" if not is_today else "dash_today_disabled",
                use_container_width=True,
                type="primary" if not is_today else "secondary",
                disabled=is_today,
                help="이미 오늘입니다" if is_today else "오늘로 이동",
            ):
                st.session_state["dash_date_picker"] = today
                st.rerun()

    # ── 데이터 로드 ───────────────────────────────────────────────────────
    target_str = str(cur_date)
    reqs = _req_list_for_date(con, project_id, target_str)

    # 시간대별(내림차순) → zone별(내림차순) 정렬
    reqs = sorted(reqs, key=lambda r: (r.get("time_from", ""), r.get("booking_zone", "")), reverse=True)

    dow_map = {0:"월요일", 1:"화요일", 2:"수요일", 3:"목요일",
               4:"금요일", 5:"토요일", 6:"일요일"}
    date_label = f"{cur_date.year}년 {cur_date.month}월 {cur_date.day}일 {dow_map[cur_date.weekday()]}"

    # ── 터미널 사용 존 목록 로드 ─────────────────────────────────────────
    import json as _json
    try:
        _terminal_zones = set(_json.loads(settings_get(con, "terminal_zones_json", '[]')))
    except Exception:
        _terminal_zones = set()

    # ── 테이블 행 생성 ────────────────────────────────────────────────────
    row_parts = []
    total_cnt = 0

    if not reqs:
        row_parts.append('<tr><td colspan="12" style="padding:30px;color:#94a3b8;">해당 날짜에 등록된 요청이 없습니다.</td></tr>')
    else:
        for i, r in enumerate(reqs, 1):
            kind     = r.get("kind", KIND_IN)
            is_in    = kind == KIND_IN
            kind_cls = "kind-in" if is_in else "kind-out"
            kind_lbl = "반입" if is_in else "반출"
            zone     = r.get("booking_zone", "")
            company  = r.get("company_name", "")
            item     = r.get("item_name", "")
            vcnt_raw = r.get("vehicle_count", "")
            vcnt     = f"{vcnt_raw}대" if vcnt_raw else ""
            vton     = r.get("vehicle_ton", "")
            loading  = r.get("loading_method", "")
            gate_raw = r.get("gate", "")
            gate_raw = "" if gate_raw == "선택" else gate_raw
            # 터미널 미사용 존이면 N/A 표기
            gate     = gate_raw if zone in _terminal_zones else "N/A"
            t_from = r.get("time_from", "")
            sup    = r.get("worker_supervisor", "")
            guide  = r.get("worker_guide", "")
            mgr    = r.get("worker_manager", "")
            vcnt_int = int(vcnt_raw) if str(vcnt_raw).isdigit() else 0
            total_cnt += vcnt_int

            tds = (
                f'<td><div style="position:relative">{i}<div class="tooltip-content">{i}</div></div></td>'
                f'<td><div style="position:relative">{zone}<div class="tooltip-content">{zone}</div></div></td>'
                f'<td><div style="position:relative">{gate}<div class="tooltip-content">{gate}</div></div></td>'
                f'<td><div style="position:relative">{company}<div class="tooltip-content">{company}</div></div></td>'
                f'<td><div style="position:relative">{item}<div class="tooltip-content">{item}</div></div></td>'
                f'<td><div style="position:relative">{vcnt}<div class="tooltip-content">{vcnt}</div></div></td>'
                f'<td><div style="position:relative"><span class="{kind_cls}">{kind_lbl}</span> / {vton}<div class="tooltip-content">{kind_lbl} / {vton}</div></div></td>'
                f'<td><div style="position:relative">{loading}<div class="tooltip-content">{loading}</div></div></td>'
                f'<td><div style="position:relative">{t_from}<div class="tooltip-content">{t_from}</div></div></td>'
                f'<td><div style="position:relative">{sup}<div class="tooltip-content">{sup}</div></div></td>'
                f'<td><div style="position:relative">{guide}<div class="tooltip-content">{guide}</div></div></td>'
                f'<td><div style="position:relative">{mgr}<div class="tooltip-content">{mgr}</div></div></td>'
            )
            row_parts.append(f'<tr>{tds}</tr>')

        # 합계 행
        row_parts.append(
            f'<tr class="total-row">'
            f'<td colspan="4" style="text-align:right;padding-right:8px;">합 계</td>'
            f'<td>{total_cnt}대</td>'
            f'<td colspan="7"></td>'
            f'</tr>'
        )

    rows_html = "".join(row_parts)

    # ── HTML 렌더링 ───────────────────────────────────────────────────────
    thead = (
        '<thead>'
        '<tr>'
        '<th>No</th>'
        '<th>Zone</th>'
        '<th>터미널</th>'
        '<th>업체명</th>'
        '<th>자재종류</th>'
        '<th>수량</th>'
        '<th>반입·반출<br>차량</th>'
        '<th>상·하차<br>방식</th>'
        '<th>시간</th>'
        '<th>작업<br>지휘자</th>'
        '<th>유도원</th>'
        '<th>담당자</th>'
        '</tr>'
        '</thead>'
    )
    cnt_summary = f"총 {len(reqs)}건 (반입 {sum(1 for r in reqs if r.get('kind')==KIND_IN)}건 / 반출 {sum(1 for r in reqs if r.get('kind')==KIND_OUT)}건)" if reqs else "등록된 요청 없음"
    mobile_html = (
        f'<div class="dash-mobile-only">'
        f'<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:20px;text-align:center;">'
        f'<div style="font-size:15px;font-weight:700;color:#0f172a;margin-bottom:6px;">자재 상·하차 반입/반출 현황</div>'
        f'<div style="font-size:13px;color:#475569;margin-bottom:4px;">□ 현장명 : {site_name}</div>'
        f'<div style="font-size:13px;color:#475569;margin-bottom:12px;">{date_label}</div>'
        f'<div style="font-size:13px;color:#2563eb;font-weight:600;">{cnt_summary}</div>'
        f'</div>'
        f'</div>'
    )
    html = (
        '<div class="dash-wrap">'
        '<div class="dash-title-box"><h2>자재 상 · 하차 반입 / 반출 현황</h2></div>'
        f'<div class="dash-meta"><span>□ 현장명 : {site_name}</span><span>{date_label}</span></div>'
        f'<table class="dash-table">{thead}<tbody>{rows_html}</tbody></table>'
        '</div>'
        f'{mobile_html}'
    )
    st.markdown(html, unsafe_allow_html=True)

    # 드래그-스크롤: .dash-wrap 위에서 마우스 클릭 드래그로 가로 이동
    st.markdown("""
<script>
(function(){
  function initDrag(el){
    let isDown=false, startX=0, scrollLeft=0;
    el.addEventListener('mousedown',function(e){
      if(e.button!==0) return;
      isDown=true; startX=e.pageX-el.offsetLeft; scrollLeft=el.scrollLeft;
      e.preventDefault();
    });
    el.addEventListener('mouseleave',function(){ isDown=false; });
    el.addEventListener('mouseup',function(){ isDown=false; });
    el.addEventListener('mousemove',function(e){
      if(!isDown) return;
      var x=e.pageX-el.offsetLeft, walk=(x-startX)*1.2;
      el.scrollLeft=scrollLeft-walk;
    });
  }
  function tryInit(){
    var el=document.querySelector('.dash-wrap');
    if(el){ initDrag(el); } else { setTimeout(tryInit,300); }
  }
  tryInit();
})();
</script>
""", unsafe_allow_html=True)

    # ── 엑셀 다운로드 버튼 ────────────────────────────────────────────────
    st.markdown("<div style='margin-top:28px;'></div>", unsafe_allow_html=True)
    if reqs:
        try:
            excel_bytes = _build_excel(reqs, site_name, date_label, _terminal_zones)
            filename = f"반입반출현황_{target_str}.xlsx"
            _, btn_col, _ = st.columns([1.5, 2, 1.5])
            with btn_col:
                st.download_button(
                    label="📥 엑셀 다운로드",
                    data=excel_bytes,
                    file_name=filename,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                )
        except ImportError:
            st.warning("엑셀 다운로드를 사용하려면 `pip install openpyxl` 을 실행하세요.")
