"""Unified 계획 page — schedule timeline + request form side by side."""
import json
import uuid
import streamlit as st
from shared.timing import measure
from shared import audit as _audit
from datetime import date, timedelta

from modules.schedule.crud import schedule_list_by_date, schedule_sync_from_requests, schedule_insert
from modules.schedule.components.timeline import render_timeline, BLOCKING_STATUSES
from modules.schedule.components.dnd_timeline import dnd_timeline
from modules.schedule.components.summary import render_daily_summary
from modules.schedule.css.schedule import get_schedule_css
from modules.request.crud import req_insert, req_update_time, req_get
from modules.approval.crud import approvals_create_default
from modules.schedule.crud import schedule_delete, schedule_update, schedule_get
from shared.helpers import now_str, req_display_id, today_kst
from db.models import settings_get
from config import KIND_IN, KIND_OUT, VEHICLE_TONS, GATE_ZONES, TIME_SLOTS

_ITEM_TYPES = [
    "파이프류 (3m 미만)",
    "파이프류 (3m 이상)",
    "블럭/벽돌",
    "시멘트류",
    "타일류",
    "목창호",
    "몰드바",
    "에어컨",
    "기타",
]

_LOADING_TYPES = ["지게차", "인력", "직접입력"]


def _insert_extra_slots(con, project_id, sel_list, add_slots, kind_val, gate,
                        company_name, vehicle_info, created_by) -> int:
    """수정 모드에서 추가 선택된 빈 슬롯을 기존 req_id에 삽입. 삽입된 슬롯 수 반환."""
    if not add_slots or not sel_list:
        return 0
    ref      = sel_list[0]
    rid      = ref.get("req_id", "")
    sdate    = ref.get("schedule_date", "")
    bzone    = ref.get("booking_zone", "A")
    if not rid or not sdate:
        return 0
    _ex = (con.table("schedules").select("time_from")
           .eq("req_id", rid).eq("schedule_date", sdate).execute())
    existing_tf = {r["time_from"] for r in (_ex.data or [])}
    n_added = 0
    for slot in add_slots:
        if slot in existing_tf:
            continue
        try:
            idx = TIME_SLOTS.index(slot)
        except ValueError:
            continue
        if idx + 1 >= len(TIME_SLOTS):
            continue
        schedule_insert(con, project_id, {
            "req_id":        rid,
            "title":         company_name,
            "schedule_date": sdate,
            "time_from":     slot,
            "time_to":       TIME_SLOTS[idx + 1],
            "kind":          kind_val,
            "gate":          gate,
            "company_name":  company_name,
            "vehicle_info":  vehicle_info,
            "status":        ref.get("status", "PENDING"),
            "color":         ref.get("color", "#fbbf24"),
            "created_by":    created_by,
            "booking_zone":  bzone,
        })
        n_added += 1
    # request time_from/time_to 범위 갱신
    if n_added:
        _all_res = (con.table("schedules").select("time_from")
                    .eq("req_id", rid).eq("schedule_date", sdate)
                    .order("time_from").execute())
        all_tf = [r["time_from"] for r in (_all_res.data or [])]
        if all_tf:
            last_idx = TIME_SLOTS.index(all_tf[-1]) if all_tf[-1] in TIME_SLOTS else 0
            _new_to = TIME_SLOTS[min(last_idx + 1, len(TIME_SLOTS) - 1)]
            con.table("requests").update({
                "time_from": all_tf[0],
                "time_to": _new_to,
            }).eq("id", rid).execute()
            _prev_tf = sorted(existing_tf)
            _audit.log_change(
                con, project_id=project_id, req_id=rid, action=_audit.ADD_SLOT,
                before_from=_prev_tf[0] if _prev_tf else "",
                before_to=_prev_tf[-1] if _prev_tf else "",
                after_from=all_tf[0], after_to=_new_to,
                detail={"date": sdate, "added": n_added,
                        "added_slots": sorted(add_slots)},
            )
    return n_added


def _sel_range(sel_list):
    """선택된 슬롯 목록의 실제 시간 범위 (시작 time_from ~ 끝 time_to)."""
    tf = sorted(s.get("time_from", "") for s in sel_list if s.get("time_from"))
    tt = sorted(s.get("time_to", "")   for s in sel_list if s.get("time_to"))
    return (tf[0] if tf else ""), (tt[-1] if tt else "")


def _shift_group_slots(con, group, start_fi):
    """연속 슬롯 그룹을 start_fi 부터 재배치.

    schedules_req_slot_uniq (req_id, time_from, time_to) 유니크 인덱스와
    중간 상태에서 충돌하지 않도록, 뒤로 이동할 때는 마지막 행부터,
    앞으로 이동할 때는 첫 행부터 갱신한다.
    """
    if not group:
        return
    try:
        cur_fi = TIME_SLOTS.index(group[0].get("time_from", ""))
    except ValueError:
        cur_fi = start_fi
    idxs = range(len(group))
    if start_fi > cur_fi:          # 뒤로 이동 → 뒤에서부터
        idxs = reversed(list(idxs))
    for i in idxs:
        nfi = start_fi + i
        if nfi + 1 >= len(TIME_SLOTS):
            continue
        schedule_update(con, group[i]["id"],
                        time_from=TIME_SLOTS[nfi], time_to=TIME_SLOTS[nfi + 1])


def _consecutive_toggle(slots: list, new_slot: str) -> list:
    """슬롯 선택/해제 — 항상 연속 구간 유지.
    - 미선택 슬롯 클릭: 기존 범위와 새 슬롯 사이를 모두 채워 확장
    - 경계(첫/마지막) 슬롯 클릭: 한 칸 축소
    - 중간 슬롯 클릭: 해당 슬롯으로 초기화
    - 단일 선택 슬롯 클릭: 전체 해제
    """
    if new_slot not in slots:
        if not slots:
            return [new_slot]
        try:
            new_idx = TIME_SLOTS.index(new_slot)
            lo = min(TIME_SLOTS.index(x) for x in slots)
            hi = max(TIME_SLOTS.index(x) for x in slots)
            lo, hi = min(lo, new_idx), max(hi, new_idx)
            return [TIME_SLOTS[i] for i in range(lo, hi + 1)]
        except ValueError:
            return [new_slot]
    else:
        s = sorted(slots)
        if len(s) == 1:
            return []
        if new_slot == s[0] or new_slot == s[-1]:
            return [x for x in s if x != new_slot]
        return [new_slot]


def _slot_range(slots: list) -> tuple[str, str]:
    """정렬된 슬롯 리스트에서 time_from, time_to 계산 (폼 제출용)."""
    if not slots:
        return "08:00", "08:30"
    s = sorted(slots)
    t_from = s[0]
    last_idx = TIME_SLOTS.index(s[-1]) if s[-1] in TIME_SLOTS else 4
    t_to = TIME_SLOTS[min(last_idx + 1, len(TIME_SLOTS) - 1)]
    return t_from, t_to


def _format_slot_ranges(slots: list) -> str:
    """슬롯 리스트를 연속 구간으로 묶어 표시. 예) 09:00~09:30, 10:00~11:00"""
    if not slots:
        return "미선택"
    s = sorted(slots)
    groups, group = [], [s[0]]
    for slot in s[1:]:
        try:
            prev_i = TIME_SLOTS.index(group[-1])
            curr_i = TIME_SLOTS.index(slot)
            if curr_i == prev_i + 1:
                group.append(slot)
                continue
        except ValueError:
            pass
        groups.append(group)
        group = [slot]
    groups.append(group)

    parts = []
    for grp in groups:
        t_from = grp[0]
        try:
            last_i = TIME_SLOTS.index(grp[-1])
            t_to   = TIME_SLOTS[min(last_i + 1, len(TIME_SLOTS) - 1)]
        except ValueError:
            t_to = t_from
        parts.append(f"{t_from}~{t_to}")
    return ", ".join(parts)


def _has_conflict(slots: list, schedules: list, kind_val: str) -> bool:
    """선택된 슬롯 중 이미 예약된 슬롯이 있으면 True."""
    booked = [
        s for s in schedules
        if s.get("kind") == kind_val and s.get("status") in BLOCKING_STATUSES
    ]
    for slot in slots:
        if any(b["time_from"] <= slot < b["time_to"] for b in booked):
            return True
    return False


@st.dialog("🅿️ 터미널 상태 변경")
def _terminal_status_dialog(terminal: str, in_n: int, is_freed: bool,
                             project_id: str, date_str: str, con, hold=None) -> None:
    """팝업: 터미널 해제 / 재점유 확인. hold 지정 시 다중일 보관 안내(읽기전용)."""
    st.markdown("""<style>
    [data-testid="stDialog"] button {
        min-height: 44px !important;
        height: 44px !important;
        font-size: 15px !important;
    }
    [data-testid="stDialog"] button p { margin: 0 !important; }
    </style>""", unsafe_allow_html=True)

    # 다중일 보관(다른 날짜 반입) — 날짜 해제로는 안 풀리므로 안내만 표시
    if hold:
        _co = hold.get("company") or "-"
        _it = hold.get("item") or "-"
        _ds = (hold.get("start") or "")[:10]
        _de = (hold.get("end") or "")[:10]
        st.markdown(
            f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:10px;">'
            f'<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#f59e0b;flex-shrink:0;"></span>'
            f'<span style="font-size:16px;font-weight:700;">{terminal}</span>'
            f'<span style="font-size:13px;color:#64748b;">보관 중</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
        st.markdown(f"**업체** {_co} &nbsp;·&nbsp; **자재** {_it}", unsafe_allow_html=True)
        st.caption(f"보관 기간 {_ds} ~ {_de} (다른 날짜 반입 건)")
        _is_admin = st.session_state.get("IS_ADMIN", False)
        _hrid = str(hold.get("rid") or "")
        if _is_admin and _hrid and not _hrid.startswith("_md_"):
            st.info("자재가 빠졌다면 보관을 종료해 점유를 즉시 해제할 수 있습니다.")
            _ra, _rb = st.columns(2)
            with _ra:
                if st.button("📦 보관 종료(해제)", type="primary", use_container_width=True):
                    from shared.storage_plan import release_storage
                    release_storage(con, _hrid)
                    st.session_state.pop("_term_dlg_trigger", None)
                    st.toast(f"{terminal} 보관이 종료되어 점유가 해제되었습니다.", icon="📦")
                    st.rerun()
            with _rb:
                if st.button("닫기", use_container_width=True):
                    st.session_state.pop("_term_dlg_trigger", None)
                    st.rerun()
        else:
            st.info("보관 기간 동안 이 터미널은 신청할 수 없습니다. "
                    "해제는 관리자 또는 해당 자재의 반출/저장 위치 관리에서 처리하세요.")
            if st.button("닫기", use_container_width=True):
                st.session_state.pop("_term_dlg_trigger", None)
                st.rerun()
        return

    _dot_c  = "#f59e0b" if in_n > 0 else "#22c55e"
    _status = f"반입 {in_n}건 보관 중" if in_n > 0 else "여유"
    st.markdown(
        f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:10px;">'
        f'<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:{_dot_c};flex-shrink:0;"></span>'
        f'<span style="font-size:16px;font-weight:700;">{terminal}</span>'
        f'<span style="font-size:13px;color:#64748b;">{_status}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )
    if in_n > 0:
        # 이전 해제 기록이 남아있으면 자동 초기화 (신규 신청이 들어온 것이므로)
        if is_freed:
            (con.table("terminal_releases").delete()
             .eq("project_id", project_id).eq("terminal", terminal)
             .eq("release_date", date_str).execute())
        st.caption("자재가 야적장으로 이동 완료되면 해제하세요.")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("🔓 해제", type="primary", use_container_width=True):
                con.table("terminal_releases").upsert({
                    "id": uuid.uuid4().hex,
                    "project_id": project_id,
                    "terminal": terminal,
                    "release_date": date_str,
                    "created_at": now_str(),
                    "created_by": st.session_state.get("USER_NAME", ""),
                }, on_conflict="project_id,terminal,release_date",
                    ignore_duplicates=True).execute()
                st.session_state.pop("_term_dlg_trigger", None)
                st.rerun()
        with c2:
            if st.button("취소", use_container_width=True):
                st.session_state.pop("_term_dlg_trigger", None)
                st.rerun()
    else:
        st.info("현재 예약이 없는 여유 터미널입니다.")
        if st.button("닫기", use_container_width=True):
            st.session_state.pop("_term_dlg_trigger", None)
            st.rerun()


def _max_date_skip_sunday(base: date, advance_days: int) -> date:
    """오늘부터 advance_days 영업일(일요일 제외) 후 날짜를 반환."""
    d = base
    counted = 0
    while counted < advance_days:
        d += timedelta(days=1)
        if d.weekday() != 6:  # 일요일(6) 제외
            counted += 1
    return d


@measure("page.schedule")


def page_schedule(con):
    """Unified schedule calendar + request registration — single screen."""
    st.markdown(f"<style>{get_schedule_css()}</style>", unsafe_allow_html=True)

    project_id = st.session_state.get("PROJECT_ID", "default")
    is_admin   = st.session_state.get("IS_ADMIN", False)
    user_name  = st.session_state.get("USER_NAME", "")

    # ── 작업 처리 세션 키 ─────────────────────────────────────────────────────
    _ADMIN_KEYS = ("admin_sel_sched_ids", "admin_sel_sched_list", "admin_sel_sched_kind")
    _USER_KEYS  = ("user_sel_sched_list",)

    # DnD 그룹 이동 처리 (드래그)
    if "admin_dnd_move" in st.session_state:
        mv = st.session_state.pop("admin_dnd_move")
        req_id     = mv.get("req_id")
        drag_index = mv.get("drag_index", 0)
        to_slot    = mv.get("to_slot", "")
        try:
            drop_fi = TIME_SLOTS.index(to_slot)
        except ValueError:
            drop_fi = 0
        start_fi = max(0, drop_fi - drag_index)
        date_str = str(st.session_state.get("sched_current_date", today_kst()))
        if req_id:
            _gres = (con.table("schedules").select("*")
                     .eq("req_id", req_id).eq("schedule_date", date_str)
                     .order("time_from").execute())
            group = _gres.data or []
            _bf, _bt = _audit.slot_range(group)
            _shift_group_slots(con, group, start_fi)
            if group:
                actual_end = min(start_fi + len(group), len(TIME_SLOTS) - 1)
                con.table("requests").update({
                    "time_from": TIME_SLOTS[start_fi],
                    "time_to": TIME_SLOTS[actual_end],
                }).eq("id", req_id).execute()
                _audit.log_change(
                    con, project_id=project_id, req_id=req_id, action=_audit.MOVE,
                    before_from=_bf, before_to=_bt,
                    after_from=TIME_SLOTS[start_fi], after_to=TIME_SLOTS[actual_end],
                    detail={"via": "drag", "date": date_str, "slots": len(group)},
                )
        else:
            nf = TIME_SLOTS[drop_fi]
            nt = TIME_SLOTS[min(drop_fi + 1, len(TIME_SLOTS) - 1)]
            _one = schedule_get(con, mv["sched_id"]) or {}
            schedule_update(con, mv["sched_id"], time_from=nf, time_to=nt)
            _audit.log_change(
                con, project_id=project_id, req_id="", action=_audit.MOVE,
                before_from=_one.get("time_from", ""), before_to=_one.get("time_to", ""),
                after_from=nf, after_to=nt,
                detail={"via": "drag", "sched_id": mv["sched_id"], "date": date_str},
            )
        st.rerun()

    # 단일 슬롯 삭제 (× 버튼)
    if "admin_del_single_slot" in st.session_state:
        sid = st.session_state.pop("admin_del_single_slot")
        del_sched = schedule_get(con, sid)
        if del_sched:
            req_id   = del_sched.get("req_id")
            date_str = del_sched.get("schedule_date")
            _rres = (con.table("schedules").select("*")
                     .eq("req_id", req_id).eq("schedule_date", date_str)
                     .neq("id", sid).order("time_from").execute())
            remaining = _rres.data or []
            schedule_delete(con, sid)
            if remaining and req_id:
                con.table("requests").update({
                    "time_from": remaining[0]["time_from"],
                    "time_to": remaining[-1]["time_to"],
                }).eq("id", req_id).execute()
            _audit.log_change(
                con, project_id=project_id, req_id=req_id or "",
                action=_audit.DELETE_SLOT,
                before_from=del_sched.get("time_from", ""),
                before_to=del_sched.get("time_to", ""),
                after_from=remaining[0]["time_from"] if remaining else "",
                after_to=remaining[-1]["time_to"] if remaining else "",
                detail={"date": date_str, "deleted_slot_id": sid,
                        "remaining": len(remaining)},
            )
        for k in _ADMIN_KEYS:
            st.session_state.pop(k, None)
        st.session_state.pop("sched_edit_from_home", None)
        st.rerun()

    if "admin_del_sched" in st.session_state:
        for sid in st.session_state.pop("admin_del_sched"):
            _d = schedule_get(con, sid) or {}
            schedule_delete(con, sid)
            _audit.log_change(
                con, project_id=project_id, req_id=_d.get("req_id", ""),
                action=_audit.DELETE,
                before_from=_d.get("time_from", ""), before_to=_d.get("time_to", ""),
                detail={"date": _d.get("schedule_date", ""), "sched_id": sid,
                        "company": _d.get("company_name", "")},
            )
        for k in _ADMIN_KEYS:
            st.session_state.pop(k, None)
        st.session_state.pop("sched_edit_from_home", None)
        st.rerun()

    if "admin_move_slot" in st.session_state:
        move_slot = st.session_state.pop("admin_move_slot")
        st.session_state.pop("admin_move_kind", None)
        sel_list  = sorted(st.session_state.get("admin_sel_sched_list", []),
                           key=lambda s: s.get("time_from", ""))
        try:
            start_fi = TIME_SLOTS.index(move_slot)
        except ValueError:
            start_fi = 0
        _mv_date = str(st.session_state.get("sched_current_date", today_kst()))
        # 선택된 슬롯의 req_id 수집 (연속 그룹 이동)
        _mv_req_ids = [s.get("req_id") for s in sel_list if s.get("req_id")]
        if _mv_req_ids:
            # req_id 기준으로 해당 날짜의 ALL 슬롯을 연속 배치
            _seen = set()
            for _req_id in _mv_req_ids:
                if _req_id in _seen:
                    continue
                _seen.add(_req_id)
                _gres2 = (con.table("schedules").select("*")
                          .eq("req_id", _req_id).eq("schedule_date", _mv_date)
                          .order("time_from").execute())
                _group = _gres2.data or []
                _bf2, _bt2 = _audit.slot_range(_group)
                _shift_group_slots(con, _group, start_fi)
                if _group:
                    _actual_end = min(start_fi + len(_group), len(TIME_SLOTS) - 1)
                    con.table("requests").update({
                        "time_from": TIME_SLOTS[start_fi],
                        "time_to": TIME_SLOTS[_actual_end],
                    }).eq("id", _req_id).execute()
                    _audit.log_change(
                        con, project_id=project_id, req_id=_req_id,
                        action=_audit.MOVE,
                        before_from=_bf2, before_to=_bt2,
                        after_from=TIME_SLOTS[start_fi],
                        after_to=TIME_SLOTS[_actual_end],
                        detail={"via": "move_button", "date": _mv_date,
                                "slots": len(_group)},
                    )
        else:
            # req_id 없는 단독 슬롯은 개별 이동
            for i, sched in enumerate(sel_list):
                nfi = start_fi + i
                if nfi + 1 >= len(TIME_SLOTS):
                    break
                schedule_update(con, sched["id"],
                                time_from=TIME_SLOTS[nfi], time_to=TIME_SLOTS[nfi + 1])
        for k in _ADMIN_KEYS:
            st.session_state.pop(k, None)
        st.session_state.pop("sched_edit_from_home", None)
        st.rerun()

    # 세션 초기화
    for key, default in [
        ("sched_current_date",     today_kst()),
        ("sched_sel_in_slots",     []),
        ("sched_sel_out_slots",    []),
        ("sched_last_kind",        "반입"),
        ("user_sel_sched_list",    []),
        ("sched_mobile_show_form", False),
        ("sched_current_zone",     None),
    ]:
        if key not in st.session_state:
            st.session_state[key] = default

    # 전일/익일 버튼 클릭으로 예약된 날짜를 위젯 렌더 전에 반영
    if "sched_pending_date" in st.session_state:
        st.session_state["sched_date_pick"] = st.session_state.pop("sched_pending_date")

    current_date = st.session_state["sched_current_date"]
    # 세션에 저장된 날짜가 오늘보다 과거면 오늘로 자동 보정
    if current_date < today_kst():
        current_date = today_kst()
        st.session_state["sched_current_date"] = current_date
    schedule_sync_from_requests(con, project_id)
    date_str = current_date.isoformat()

    # ── 예약존 로드 ────────────────────────────────────────────────────────
    try:
        _bz_all  = json.loads(settings_get(con, "booking_zones_json", '["A"]'))
        _bz_dis  = json.loads(settings_get(con, "booking_zones_disabled_json", "[]"))
        booking_zones = [z for z in _bz_all if z not in _bz_dis] or ["A"]
    except Exception:
        booking_zones = ["A"]

    if st.session_state.get("sched_current_zone") not in booking_zones:
        st.session_state["sched_current_zone"] = booking_zones[0]
    current_zone = st.session_state["sched_current_zone"]

    # ── 관리자 전체 존 현황 그리드 ─────────────────────────────────────────
    _all_scheds = None   # 전체 존 조회 결과 — 존별 필터에 재사용
    if is_admin and len(booking_zones) > 1:
        _all_scheds = schedule_list_by_date(con, project_id, date_str)
        _zone_summary = {}
        for bz in booking_zones:
            _zs = [s for s in _all_scheds if s.get("booking_zone") == bz]
            _in_cnt  = len({s["req_id"] for s in _zs if s.get("kind") == KIND_IN  and s.get("req_id")})
            _out_cnt = len({s["req_id"] for s in _zs if s.get("kind") == KIND_OUT and s.get("req_id")})
            _zone_summary[bz] = (_in_cnt, _out_cnt)
        _th = "".join(
            f'<th style="padding:6px 10px;text-align:center;background:#1e3a8a;color:#fff;font-size:13px;">'
            f'{bz}</th>' for bz in booking_zones
        )
        _td = "".join(
            f'<td style="padding:6px 10px;text-align:center;font-size:12px;'
            f'background:{"#f0fdf4" if _zone_summary[bz][0]+_zone_summary[bz][1]>0 else "#f8fafc"};">'
            f'{"<span style=\'color:#1d4ed8;font-weight:600;\'>반입 " + str(_zone_summary[bz][0]) + "건</span>" if _zone_summary[bz][0] else ""}'
            f'{"<br>" if _zone_summary[bz][0] and _zone_summary[bz][1] else ""}'
            f'{"<span style=\'color:#dc2626;font-weight:600;\'>반출 " + str(_zone_summary[bz][1]) + "건</span>" if _zone_summary[bz][1] else ""}'
            f'{"—" if not _zone_summary[bz][0] and not _zone_summary[bz][1] else ""}'
            f'</td>'
            for bz in booking_zones
        )
        st.markdown(
            f'<div style="overflow-x:auto;margin-bottom:8px;">'
            f'<table style="width:100%;border-collapse:collapse;border:1px solid #e2e8f0;border-radius:8px;overflow:hidden;">'
            f'<tr>{_th}</tr><tr>{_td}</tr>'
            f'</table></div>',
            unsafe_allow_html=True,
        )

    # ── 도면 보기 (참조용 expander) ──────────────────────────────────────
    try:
        from shared.storage_plan import floor_image as _floor_image
        _img_g, _img_b1, _img_b2 = _floor_image("ground"), _floor_image("b1"), _floor_image("b2")
        if _img_g or _img_b1 or _img_b2:
            with st.expander("🗺 도면 보기 (지상 · B1F · B2F)"):
                _t_g, _t_b1, _t_b2 = st.tabs(["지상(하역)", "B1F(보관)", "B2F(보관)"])
                with _t_g:
                    if _img_g: st.image(_img_g, use_container_width=True)
                with _t_b1:
                    if _img_b1: st.image(_img_b1, use_container_width=True)
                with _t_b2:
                    if _img_b2: st.image(_img_b2, use_container_width=True)
    except Exception:
        pass

    # ── 존 선택 버튼 (2개 이상일 때만) ────────────────────────────────────
    if len(booking_zones) > 1:
        st.markdown("""<style>
        .st-key-zone_sel_row .stHorizontalBlock { gap: 4px !important; flex-wrap: wrap !important; }
        [class*="st-key-zone_btn_"] button {
            min-height: 36px !important; height: 36px !important;
            font-size: 13px !important; font-weight: 600 !important;
            padding: 0 8px !important;
        }
        [class*="st-key-zone_btn_"] button p { margin: 0 !important; line-height: 1 !important; }
        </style>""", unsafe_allow_html=True)
        with st.container(key="zone_sel_row"):
            _zcols = st.columns(len(booking_zones))
            for _zi, _bz in enumerate(booking_zones):
                with _zcols[_zi]:
                    _is_cur = (_bz == current_zone)
                    with st.container(key=f"zone_btn_{_zi}"):
                        if st.button(
                            f"{'✓ ' if _is_cur else ''}{_bz}",
                            key=f"zsel_{_zi}",
                            type="primary" if _is_cur else "secondary",
                            use_container_width=True,
                        ):
                            st.session_state["sched_current_zone"]  = _bz
                            st.session_state["sched_sel_in_slots"]  = []
                            st.session_state["sched_sel_out_slots"] = []
                            st.session_state["user_sel_sched_list"] = []
                            st.session_state.pop("admin_sel_sched_ids",  None)
                            st.session_state.pop("admin_sel_sched_list", None)
                            st.session_state.pop("sched_edit_from_home", None)
                            st.rerun()
        st.markdown("<div style='margin-top:6px'></div>", unsafe_allow_html=True)

    col_left, col_right = st.columns([3, 2], gap="large")
    _occupied_terminals: set = set()   # 당일 점유 중 터미널 (드롭다운 필터용)

    # ── 모바일: 타임라인 ↔ 폼 전환 CSS ──────────────────────────────────────
    _mbf = st.session_state.get("sched_mobile_show_form", False)
    _hide_tl   = "[data-testid='stColumn']:has([class*='st-key-sched_nav_row']){display:none!important}"
    _hide_form = "[data-testid='stColumn']:has([class*='st-key-sched_back_to_timeline']){display:none!important}"
    _show_back = ".st-key-sched_back_to_timeline{display:block!important;margin-bottom:8px!important}"
    _btn_size  = ".st-key-sched_back_to_timeline button,.st-key-sched_go_form_wrap button{min-height:44px!important;height:44px!important;font-size:15px!important;width:100%!important;display:flex!important;align-items:center!important;justify-content:center!important;} .st-key-sched_back_to_timeline button p,.st-key-sched_go_form_wrap button p{margin:0!important;line-height:1!important}"
    st.markdown(f"""<style>
    .st-key-sched_back_to_timeline{{display:none!important}}
    @media(max-width:480px){{
        {_hide_tl if _mbf else _hide_form}
        {_show_back if _mbf else ""}
        {_btn_size}
    }}
    </style>""", unsafe_allow_html=True)

    # ── LEFT: 날짜 네비 + 타임라인 ───────────────────────────────────────────
    with col_left:
        st.markdown("#### 📅 일정 현황")

        st.markdown("""<style>
        .st-key-sched_prev button,
        .st-key-sched_next button {
            height: 38px !important;
            min-height: 38px !important;
            padding-top: 0 !important;
            padding-bottom: 0 !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
        }
        .st-key-sched_prev button p,
        .st-key-sched_next button p {
            line-height: 1 !important;
            margin: 0 !important;
            padding: 0 !important;
        }
        .st-key-sched_nav_row .stHorizontalBlock {
            align-items: center !important;
        }
        .st-key-sched_nav_row .stHorizontalBlock > div {
            display: flex !important;
            align-items: center !important;
        }
        </style>""", unsafe_allow_html=True)
        with st.container(key="sched_nav_row"):
            nav1, nav2, nav3 = st.columns([1, 1.75, 1])
            with nav1:
                today = today_kst()
                _adv = int(settings_get(con, "schedule_advance_days", "2"))
                max_date = today + timedelta(days=90) if is_admin else _max_date_skip_sunday(today, _adv)
                if st.button("‹ 전일", key="sched_prev", use_container_width=True,
                             disabled=(current_date <= today)):
                    new_date = current_date - timedelta(days=1)
                    st.session_state["sched_current_date"]    = new_date
                    st.session_state["sched_pending_date"]    = new_date
                    st.session_state["sched_sel_in_slots"]    = []
                    st.session_state["sched_sel_out_slots"]   = []
                    st.session_state["user_sel_sched_list"]   = []
                    st.session_state["sched_mobile_show_form"] = False
                    st.session_state.pop("sched_edit_from_home", None)
                    st.session_state.pop("admin_sel_sched_ids",  None)
                    st.session_state.pop("admin_sel_sched_list", None)
                    st.session_state.pop("admin_sel_sched_kind", None)
                    st.rerun()
            with nav2:
                today = today_kst()
                _adv = int(settings_get(con, "schedule_advance_days", "2"))
                max_date = today + timedelta(days=90) if is_admin else _max_date_skip_sunday(today, _adv)
                _wd_list = ["월", "화", "수", "목", "금", "토", "일"]
                _wd       = _wd_list[current_date.weekday()]
                _is_sun   = current_date.weekday() == 6
                _bg       = "#fee2e2" if _is_sun else "#dbeafe"
                _fg       = "#b91c1c" if _is_sun else "#1d4ed8"
                _date_disp = current_date.strftime("%Y/%m/%d")
                # 표시용 박스
                st.markdown(
                    f'<div style="background:{_bg};border:1px solid #d1d5db;border-radius:6px;'
                    f'height:38px;display:flex;align-items:center;justify-content:center;'
                    f'font-size:14px;font-weight:600;color:{_fg};">'
                    f'{_date_disp} ({_wd})</div>',
                    unsafe_allow_html=True,
                )
                # 투명 date_input을 표시 박스 위로 겹침 (달력 클릭용)
                st.markdown(f"""<style>
                .st-key-sched_date_pick {{
                    margin-top: -42px !important;
                    position: relative !important;
                    z-index: 10 !important;
                    opacity: 0 !important;
                }}
                </style>""", unsafe_allow_html=True)
                picked = st.date_input(
                    "날짜", value=current_date,
                    min_value=today,
                    max_value=max_date,
                    key="sched_date_pick", label_visibility="collapsed",
                )
                if picked != current_date:
                    st.session_state["sched_current_date"]    = picked
                    st.session_state["sched_sel_in_slots"]    = []
                    st.session_state["sched_sel_out_slots"]   = []
                    st.session_state["user_sel_sched_list"]   = []
                    st.session_state["sched_mobile_show_form"] = False
                    st.session_state.pop("sched_edit_from_home", None)
                    st.session_state.pop("admin_sel_sched_ids",  None)
                    st.session_state.pop("admin_sel_sched_list", None)
                    st.session_state.pop("admin_sel_sched_kind", None)
                    st.rerun()
            with nav3:
                _adv = int(settings_get(con, "schedule_advance_days", "2"))
                max_date = today_kst() + timedelta(days=90) if is_admin else _max_date_skip_sunday(today_kst(), _adv)
                if st.button("익일 ›", key="sched_next", use_container_width=True,
                             disabled=(current_date >= max_date)):
                    new_date = current_date + timedelta(days=1)
                    st.session_state["sched_current_date"]    = new_date
                    st.session_state["sched_pending_date"]    = new_date
                    st.session_state["sched_sel_in_slots"]    = []
                    st.session_state["sched_sel_out_slots"]   = []
                    st.session_state["user_sel_sched_list"]   = []
                    st.session_state["sched_mobile_show_form"] = False
                    st.session_state.pop("sched_edit_from_home", None)
                    st.session_state.pop("admin_sel_sched_ids",  None)
                    st.session_state.pop("admin_sel_sched_list", None)
                    st.session_state.pop("admin_sel_sched_kind", None)
                    st.rerun()

        st.markdown("<div style='margin-top:12px'></div>", unsafe_allow_html=True)

        # 전체 존을 이미 조회했으면 재사용 (crud 의 .eq("booking_zone", ...) 와 동일 조건)
        if _all_scheds is not None:
            schedules = [s for s in _all_scheds if s.get("booking_zone") == current_zone]
        else:
            schedules = schedule_list_by_date(con, project_id, date_str,
                                              booking_zone=current_zone)

        # schedules에 requester_name 첨부 (본인 예약 식별용)
        _req_ids = list({s["req_id"] for s in schedules if s.get("req_id")})
        _rmap = {}
        if _req_ids:
            try:
                _rres = (con.table("requests").select("id,requester_name")
                         .in_("id", _req_ids).execute())
                _rmap = {r["id"]: (r["requester_name"] or "") for r in (_rres.data or [])}
            except Exception:
                pass
        for s in schedules:
            s["requester_name"] = _rmap.get(s.get("req_id", ""), "")

        # ── 터미널 점유 현황 카드 (터미널 사용 존일 때만) ─────────────────────
        try:
            _tz_all_card      = json.loads(settings_get(con, "gate_zones_json", "[]"))
            _tz_dis_card      = json.loads(settings_get(con, "gate_zones_disabled_json", "[]"))
            _tz_opts_card     = [z for z in _tz_all_card if z not in _tz_dis_card]
            _terminal_zs_card = json.loads(settings_get(con, "terminal_zones_json", '["A"]'))
        except Exception:
            _tz_opts_card = []
            _terminal_zs_card = ["A"]

        if current_zone in _terminal_zs_card and _tz_opts_card:
            # 반입 건수 집계 — requests 직접 조회 (신청 즉시 반영)
            # booking_zone 필터 제거: terminal_zones_json으로 이미 존 제한됨
            _tocc: dict = {t: set() for t in _tz_opts_card}
            _tcomp: dict = {t: [] for t in _tz_opts_card}   # 터미널별 업체명 목록
            _overdue_terminals: set = set()   # 2일 초과 점유 터미널
            _ovd_threshold = (today_kst() - timedelta(days=2)).isoformat()
            _occ_res = (con.table("requests")
                        .select("id,gate,company_name,created_at")
                        .eq("project_id", project_id).eq("date", date_str)
                        .eq("kind", KIND_IN).neq("status", "REJECTED")
                        .not_.is_("gate", "null").neq("gate", "").neq("gate", "선택")
                        .execute())
            for _row in (_occ_res.data or []):
                _rd   = _row
                _g    = (_rd.get("gate") or "").strip()
                _rid  = _rd.get("id", "")
                _cat  = (_rd.get("created_at") or "")[:10]  # YYYY-MM-DD 부분만
                _cname = (_rd.get("company_name") or "").strip()
                if _g in _tocc and _rid:
                    _tocc[_g].add(_rid)
                    if _cname and _cname not in _tcomp[_g]:
                        _tcomp[_g].append(_cname)
                    if _cat < _ovd_threshold:   # 생성일이 2일 초과 전이면 overdue
                        _overdue_terminals.add(_g)

            # ── 다중일 점유 보강: 다른 날짜 반입이 보관기간(기본 14일) 내라 아직 보관 중인 터미널 ──
            #    occupancy_on = 반입일~보관종료(해제 전) — 저장 현황과 동일 기준
            from shared.storage_plan import occupancy_on
            _md_hold: dict = {}   # 같은 날짜 반입 없이 다중일로만 점유된 터미널 → 상세
            try:
                _md_occ = occupancy_on(con, project_id, date_str)
            except Exception:
                _md_occ = {}
            for _mt, _minfo in _md_occ.items():
                if _mt not in _tocc or _tocc[_mt]:
                    continue   # 설정 외 터미널이거나 이미 당일 반입으로 점유 표시 중
                _tocc[_mt].add(_minfo.get("rid") or f"_md_{_mt}")
                _mc = (_minfo.get("company") or "").strip()
                if _mc and _mc not in _tcomp[_mt]:
                    _tcomp[_mt].append(_mc)
                if (_minfo.get("start") or "")[:10] < _ovd_threshold:
                    _overdue_terminals.add(_mt)
                _md_hold[_mt] = _minfo

            # 드롭다운 필터용: 점유 중 터미널 집합 (당일 반입 + 다중일 보관)
            _occupied_terminals = {t for t, rids in _tocc.items() if rids}

            # 당일 해제된 터미널 목록 조회
            _tr_res = (con.table("terminal_releases").select("terminal")
                       .eq("project_id", project_id).eq("release_date", date_str)
                       .execute())
            _released = {r["terminal"] for r in (_tr_res.data or [])}


            # 팝업 다이얼로그 트리거
            if st.session_state.pop("_term_dlg_trigger", False):
                _terminal_status_dialog(
                    st.session_state.get("_term_dlg_terminal", ""),
                    st.session_state.get("_term_dlg_in_n", 0),
                    st.session_state.get("_term_dlg_freed", False),
                    project_id, date_str, con,
                    hold=st.session_state.get("_term_dlg_hold"),
                )

            # CSS — 카드형 버튼 스타일
            st.markdown("""<style>
            .st-key-term_card_wrap { margin-bottom: 8px; }
            .st-key-term_card_wrap .stHorizontalBlock { gap: 4px !important; }
            .st-key-term_card_wrap [data-testid="stElementContainer"] { margin-bottom: 4px !important; }
            [class*="st-key-tcard_occ_"] button {
                background: #fef9c3 !important; border-color: #fcd34d !important;
                color: #92400e !important; text-align: center !important;
                min-height: 32px !important; height: 32px !important;
                font-size: 11px !important; padding: 0 4px !important;
                justify-content: center !important; width: 100% !important;
                border-radius: 4px !important;
            }
            [class*="st-key-tcard_free_"] button {
                background: #dcfce7 !important; border-color: #86efac !important;
                color: #15803d !important; text-align: center !important;
                min-height: 32px !important; height: 32px !important;
                font-size: 11px !important; padding: 0 4px !important;
                justify-content: center !important; width: 100% !important;
                border-radius: 4px !important;
            }
            [class*="st-key-tcard_ovd_"] button {
                background: #fee2e2 !important; border-color: #fca5a5 !important;
                color: #991b1b !important; text-align: center !important;
                min-height: 32px !important; height: 32px !important;
                padding: 0 6px !important; font-weight: 600 !important;
                justify-content: center !important; width: 100% !important;
                border-radius: 4px !important;
            }
            [class*="st-key-tcard_occ_"] button p,
            [class*="st-key-tcard_free_"] button p,
            [class*="st-key-tcard_ovd_"] button p {
                margin: 0 !important; font-size: 11px !important;
                white-space: nowrap !important; overflow: hidden !important;
                text-overflow: ellipsis !important;
            }
            </style>""", unsafe_allow_html=True)

            st.markdown('<div style="font-size:11px;font-weight:600;color:#64748b;margin-bottom:10px;">🅿️ 터미널 점유 현황</div>', unsafe_allow_html=True)
            with st.container(key="term_card_wrap"):
                _quads = [_tz_opts_card[i:i+4] for i in range(0, len(_tz_opts_card), 4)]
                for _pi, _quad in enumerate(_quads):
                    _pcols = st.columns(4)
                    for _ci, _t in enumerate(_quad):
                        _in_n    = len(_tocc[_t])
                        _freed   = _t in _released
                        # 신규 신청이 있으면 해제 여부 무관하게 점유 표시
                        _is_free = _in_n == 0
                        _is_ovd  = (not _is_free) and (_t in _overdue_terminals)
                        _cnt_txt = f" ×{_in_n}" if _in_n > 1 else ""
                        _emoji   = '🟢' if _is_free else ('🔴' if _is_ovd else '🟡')
                        _label   = f"{_emoji}  {_t}{_cnt_txt}"
                        _ctype   = "free" if _is_free else ("ovd" if _is_ovd else "occ")
                        _comp_names = _tcomp.get(_t, [])
                        _comp_txt = ", ".join(_comp_names) if _comp_names else ""
                        with _pcols[_ci]:
                            with st.container(key=f"tcard_{_ctype}_{_pi}_{_ci}"):
                                if st.button(_label, key=f"tcard_btn_{_pi}_{_ci}",
                                             use_container_width=True):
                                    if not _is_free or (_freed and _in_n > 0):
                                        st.session_state["_term_dlg_trigger"]  = True
                                        st.session_state["_term_dlg_terminal"] = _t
                                        st.session_state["_term_dlg_in_n"]     = _in_n
                                        st.session_state["_term_dlg_freed"]    = _freed
                                        st.session_state["_term_dlg_hold"]     = _md_hold.get(_t)
                                        st.rerun()
                                if _comp_txt:
                                    _ctxt_color = "#991b1b" if _is_ovd else "#92400e"
                                    st.markdown(
                                        f'<div style="font-size:10px;color:{_ctxt_color};'
                                        f'text-align:center;margin-top:-8px;margin-bottom:10px;'
                                        f'overflow:hidden;text-overflow:ellipsis;white-space:nowrap;'
                                        f'max-width:100%;" title="{_comp_txt}">{_comp_txt}</div>',
                                        unsafe_allow_html=True,
                                    )

        if is_admin:
            in_items  = [s for s in schedules if s.get("kind") == KIND_IN]
            out_items = [s for s in schedules if s.get("kind") == KIND_OUT]
            _from_home_tl  = st.session_state.get("sched_edit_from_home", False)
            _in_edit_mode  = bool(st.session_state.get("admin_sel_sched_list")) and _from_home_tl
            _has_view_sel  = bool(st.session_state.get("admin_sel_sched_ids")) and not _from_home_tl
            _add_time_mode = _has_view_sel  # 뷰 모드 슬롯 선택 시 이동 대신 추가 허용
            dnd_result = dnd_timeline(
                slots=TIME_SLOTS,
                in_schedules=in_items,
                out_schedules=out_items,
                is_admin=True,
                sel_ids=list(st.session_state.get("admin_sel_sched_ids", [])),
                sel_in_slots=st.session_state.get("sched_sel_in_slots", []),
                sel_out_slots=st.session_state.get("sched_sel_out_slots", []),
                admin_sel_kind=st.session_state.get("admin_sel_sched_kind"),
                in_edit_mode=_in_edit_mode,
                add_time_mode=_add_time_mode,
                key="admin_dnd",
            )
            # 새 이벤트인지 확인 (ts 기반 중복 방지)
            if dnd_result and dnd_result.get("ts") != st.session_state.get("_dnd_ts"):
                st.session_state["_dnd_ts"] = dnd_result["ts"]
                action = dnd_result.get("action")

                if action == "select":
                    # 관리자 슬롯 선택/해제
                    sid   = dnd_result["sched_id"]
                    kind_ = dnd_result["kind"]
                    sched_ = next((s for s in schedules if s["id"] == sid), None)
                    if sched_:
                        ids  = set(st.session_state.get("admin_sel_sched_ids", []))
                        lst  = list(st.session_state.get("admin_sel_sched_list", []))
                        prev = st.session_state.get("admin_sel_sched_kind")
                        if prev and prev != kind_:
                            ids, lst = set(), []
                        if sid in ids:
                            ids.discard(sid)
                            lst = [s for s in lst if s["id"] != sid]
                        else:
                            ids.add(sid)
                            lst.append(sched_)
                        st.session_state["admin_sel_sched_ids"]  = list(ids)
                        st.session_state["admin_sel_sched_list"] = lst
                        st.session_state["admin_sel_sched_kind"] = kind_ if ids else None
                    st.session_state.pop("sched_edit_from_home", None)
                    st.rerun()

                elif action in ("move", "move_group"):
                    # 드래그로 그룹 이동
                    st.session_state["admin_dnd_move"] = {
                        "sched_id":  dnd_result.get("sched_id"),
                        "req_id":    dnd_result.get("req_id"),
                        "drag_index": dnd_result.get("drag_index", 0),
                        "to_slot":   dnd_result["to_slot"],
                    }
                    st.rerun()

                elif action == "delete_slot":
                    st.session_state["admin_del_single_slot"] = dnd_result["sched_id"]
                    st.rerun()

                elif action == "move_click":
                    # 이동 버튼 클릭 → 선택된 모든 슬롯 이동
                    st.session_state["admin_move_slot"] = dnd_result["to_slot"]
                    st.session_state["admin_move_kind"] = dnd_result.get("kind")
                    st.rerun()

                elif action == "toggle_book":
                    key_ = "sched_sel_in_slots" if dnd_result["kind"] == KIND_IN else "sched_sel_out_slots"
                    lst  = list(st.session_state.get(key_, []))
                    new_slots = _consecutive_toggle(lst, dnd_result["slot"])
                    st.session_state[key_] = new_slots
                    st.session_state["sched_last_kind"] = "반입" if dnd_result["kind"] == KIND_IN else "반출"
                    # 신규 슬롯 선택 시 기존 스케줄 선택 상태 초기화 → 폼을 신규 예약 모드로 전환
                    st.session_state.pop("admin_sel_sched_ids",  None)
                    st.session_state.pop("admin_sel_sched_list", None)
                    st.session_state.pop("admin_sel_sched_kind", None)
                    st.session_state.pop("sched_edit_from_home", None)
                    st.rerun()
        else:
            user_sel_ids_cur = [s["id"] for s in st.session_state.get("user_sel_sched_list", [])]
            _user_has_view_sel = bool(st.session_state.get("user_sel_sched_list"))
            user_dnd = dnd_timeline(
                slots=TIME_SLOTS,
                in_schedules=[s for s in schedules if s.get("kind") == KIND_IN],
                out_schedules=[s for s in schedules if s.get("kind") == KIND_OUT],
                is_admin=False,
                sel_in_slots=st.session_state.get("sched_sel_in_slots", []),
                sel_out_slots=st.session_state.get("sched_sel_out_slots", []),
                username=user_name,
                user_sel_ids=user_sel_ids_cur,
                add_time_mode=_user_has_view_sel,
                key="user_dnd",
            )
            if user_dnd and user_dnd.get("ts") != st.session_state.get("_user_dnd_ts"):
                st.session_state["_user_dnd_ts"] = user_dnd["ts"]
                action = user_dnd.get("action")
                if action == "toggle_book":
                    key_ = "sched_sel_in_slots" if user_dnd["kind"] == KIND_IN else "sched_sel_out_slots"
                    lst  = list(st.session_state.get(key_, []))
                    new_slots = _consecutive_toggle(lst, user_dnd["slot"])
                    st.session_state[key_] = new_slots
                    st.session_state["sched_last_kind"] = "반입" if user_dnd["kind"] == KIND_IN else "반출"
                    st.rerun()
                elif action == "user_select":
                    sid   = user_dnd["sched_id"]
                    sched_ = next((s for s in schedules if s["id"] == sid), None)
                    if sched_:
                        lst = list(st.session_state.get("user_sel_sched_list", []))
                        if any(s["id"] == sid for s in lst):
                            lst = [s for s in lst if s["id"] != sid]
                        else:
                            lst = [sched_]  # 단일 선택
                        st.session_state["user_sel_sched_list"] = lst
                    st.session_state.pop("sched_edit_from_home", None)
                    st.rerun()

        # 모바일 전용 상세 입력 버튼 (daily summary 위, 타임라인과 간격 최소화)
        _sel_in  = st.session_state.get("sched_sel_in_slots",  [])
        _sel_out = st.session_state.get("sched_sel_out_slots", [])
        if _sel_in or _sel_out:
            st.markdown("""<style>
            .st-key-sched_go_form_wrap { display: none !important; }
            @media (max-width: 480px) {
                .st-key-sched_go_form_wrap { display: block !important; margin-top: -8px !important; }
            }
            </style>""", unsafe_allow_html=True)
            with st.container(key="sched_go_form_wrap"):
                if st.button("📝 상세 입력 →", key="sched_go_form_btn",
                             type="primary", use_container_width=True):
                    st.session_state["sched_mobile_show_form"] = True
                    st.rerun()

        render_daily_summary(schedules, con=con)


    # ── RIGHT: 반입·반출 예약 신청 (슬롯 선택 시 기존 정보 자동 입력) ────────
    with col_right:
        # 모바일 전용 뒤로 가기 버튼 (desktop에서는 CSS로 숨김)
        with st.container(key="sched_back_to_timeline"):
            if st.button("← 일정으로", key="sched_back_btn",
                         use_container_width=True):
                st.session_state["sched_mobile_show_form"] = False
                st.rerun()
        admin_sel_list = st.session_state.get("admin_sel_sched_list", [])
        user_sel_list  = st.session_state.get("user_sel_sched_list", []) if not is_admin else []
        _from_home     = st.session_state.get("sched_edit_from_home", False)
        # 타임라인 직접 선택도 편집 모드로 동작 (_from_home 조건 제거)
        is_admin_edit  = is_admin and bool(admin_sel_list)
        is_user_edit   = not is_admin and bool(user_sel_list)
        is_edit        = is_admin_edit or is_user_edit
        sel_list       = admin_sel_list if is_admin_edit else user_sel_list

        st.markdown("#### 📝 반입·반출 예약 신청")
        _has_sel_no_home = False  # 직접 선택도 편집 허용으로 변경
        st.components.v1.html("""
        <script>
        (function() {
            function formatPhone(v) {
                var d = v.replace(/[^0-9]/g, '').slice(0, 11);
                if (d.length >= 8) return d.slice(0,3) + '-' + d.slice(3,7) + '-' + d.slice(7);
                if (d.length >= 4) return d.slice(0,3) + '-' + d.slice(3);
                return d;
            }
            function attachPhoneFormatter() {
                var inputs = window.parent.document.querySelectorAll('input[placeholder="숫자만 (-제외)"]');
                inputs.forEach(function(inp) {
                    if (inp._phoneAttached) return;
                    inp._phoneAttached = true;
                    inp.addEventListener('input', function() {
                        var pos = inp.selectionStart;
                        var oldLen = inp.value.length;
                        var formatted = formatPhone(inp.value);
                        var setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                        setter.call(inp, formatted);
                        inp.dispatchEvent(new Event('input', {bubbles: true}));
                        var diff = formatted.length - oldLen;
                        inp.setSelectionRange(Math.max(0, pos + diff), Math.max(0, pos + diff));
                    });
                });
            }
            var observer = new MutationObserver(attachPhoneFormatter);
            observer.observe(window.parent.document.body, {childList: true, subtree: true});
            attachPhoneFormatter();
        })();
        </script>
        """, height=0)

        # ── 슬롯 선택 시: 기존 예약 정보 로드 ────────────────────────────
        if is_edit:
            n   = len(sel_list)
            ref = sel_list[0]
            req = (req_get(con, ref["req_id"]) or {}) if ref.get("req_id") else {}
            _rng_from, _rng_to = _sel_range(sel_list)
            can_delete = is_admin_edit or ref.get("status") == "PENDING"
            if is_admin_edit:
                st.caption("✏️ 내용 수정 후 저장 | 타임라인 [→ 이동]: 시간 이동")
            else:
                st.caption("✏️ 내 예약 수정 | 승인 전(대기중)만 삭제 가능")
            _edit_date = ref.get("schedule_date", str(current_date))
            st.markdown(
                f'<div style="font-size:14px;background:#fff8f4;border:1px solid #ED7D31;'
                f'border-radius:6px;padding:6px 10px;margin-bottom:8px;">'
                f'선택된 예약: <b>{_edit_date}, {_rng_from} ~ {_rng_to}</b> ({n}개 슬롯)</div>',
                unsafe_allow_html=True,
            )
            # 변경 이력
            _hist = _audit.history(con, ref.get("req_id", "")) if ref.get("req_id") else []
            if _hist:
                _act_ko = {
                    _audit.CREATE: "신규", _audit.MOVE: "시간 이동",
                    _audit.EDIT: "내용 수정", _audit.ADD_SLOT: "슬롯 연장",
                    _audit.DELETE_SLOT: "슬롯 삭제", _audit.DELETE: "삭제",
                }
                with st.expander(f"🕘 변경 이력 ({len(_hist)}건)", expanded=False):
                    for _h in reversed(_hist):
                        _who = _h.get("changed_by_name") or _h.get("changed_by") or "알 수 없음"
                        _role = _h.get("changed_by_role") or ""
                        _when = (_h.get("created_at") or "")[:16].replace("T", " ")
                        _a = _act_ko.get(_h.get("action", ""), _h.get("action", ""))
                        _bf, _bt = _h.get("before_from", ""), _h.get("before_to", "")
                        _af, _at = _h.get("after_from", ""), _h.get("after_to", "")
                        if _bf and (_bf, _bt) != (_af, _at):
                            _chg = f"{_bf}~{_bt} → <b>{_af}~{_at}</b>"
                        elif _af:
                            _chg = f"<b>{_af}~{_at}</b>"
                        else:
                            _chg = f"{_bf}~{_bt}"
                        st.markdown(
                            f'<div style="font-size:12px;padding:3px 0;'
                            f'border-bottom:1px solid #f1f5f9;">'
                            f'<span style="color:#64748b;">{_when}</span> · '
                            f'<b>{_a}</b> · {_chg} · '
                            f'<span style="color:#475569;">{_who}'
                            f'{f" ({_role})" if _role else ""}</span></div>',
                            unsafe_allow_html=True,
                        )

            # 추가 슬롯: 타임라인에서 직접 선택 (toggle_book → sched_sel_in/out_slots)
            _ref_kind    = ref.get("kind", KIND_IN)
            _add_key_now = "sched_sel_in_slots" if _ref_kind == KIND_IN else "sched_sel_out_slots"
            _cur_add     = sorted(st.session_state.get(_add_key_now, []))
            if _cur_add:
                st.markdown(
                    f'<div style="font-size:13px;background:#f0fdf4;border:1px solid #86efac;'
                    f'border-radius:6px;padding:6px 10px;margin-bottom:4px;">'
                    f'➕ 추가 예정: <b>{_format_slot_ranges(_cur_add)}</b></div>',
                    unsafe_allow_html=True,
                )
            def_company = req.get("company_name", ref.get("company_name", ""))
            def_item    = req.get("item_name", "")
            def_loading = req.get("loading_method", "")
            def_kind_i  = 0 if ref.get("kind") == KIND_IN else 1
            _gate_val   = req.get("gate", "")
            _gate_parts = _gate_val.split("|", 1) if "|" in _gate_val else [_gate_val, ""]
            def_gate_zone  = _gate_parts[0].strip()
            def_gate_place = _gate_parts[1].strip() if len(_gate_parts) > 1 else ""
            def_ton     = req.get("vehicle_ton", "")
            def_count   = str(req.get("vehicle_count", "1"))
            def_supervisor = req.get("worker_supervisor", "")
            def_guide      = req.get("worker_guide", "")
            def_manager    = req.get("worker_manager", "")
            def_notes   = req.get("notes", "")
            form_key     = f"slot_edit_{ref['id'][:8]}"
            conflict     = False
            is_view_only = False
        elif _has_sel_no_home:
            # ── 뷰 모드: 타임라인 직접 클릭 → 예약 정보 표시 (읽기 전용) ────────
            _vl   = admin_sel_list if is_admin else user_sel_list
            ref   = _vl[0]
            req   = (req_get(con, ref["req_id"]) or {}) if ref.get("req_id") else {}
            _vrng_from, _vrng_to = _sel_range(_vl)
            _vdate = ref.get("schedule_date", str(current_date))
            _vstatus_label = {
                "PENDING": "대기중", "APPROVED": "승인됨",
                "PENDING_APPROVAL": "대기중", "EXECUTING": "실행중",
                "DONE": "완료", "REJECTED": "반려됨",
            }
            _vstatus = _vstatus_label.get(ref.get("status", ""), ref.get("status", ""))
            st.caption("📋 선택된 예약 정보 | 타임라인 빈 슬롯 클릭 → 시간 연장 가능")
            st.markdown(
                f'<div style="font-size:14px;background:#f0f9ff;border:1px solid #bae6fd;'
                f'border-radius:6px;padding:6px 10px;margin-bottom:8px;">'
                f'선택된 예약: <b>{_vdate}, {_vrng_from} ~ {_vrng_to}</b>'
                f'<span style="float:right;background:#dbeafe;color:#1d4ed8;font-size:11px;'
                f'padding:2px 8px;border-radius:10px;">{_vstatus}</span></div>',
                unsafe_allow_html=True,
            )
            # 추가 슬롯 선택 표시 (view 모드에서 시간 연장)
            _vref_kind  = ref.get("kind", KIND_IN)
            _vadd_key   = "sched_sel_in_slots" if _vref_kind == KIND_IN else "sched_sel_out_slots"
            _vcur_add_v = sorted(st.session_state.get(_vadd_key, []))
            if _vcur_add_v:
                st.markdown(
                    f'<div style="font-size:13px;background:#f0fdf4;border:1px solid #86efac;'
                    f'border-radius:6px;padding:6px 10px;margin-bottom:4px;">'
                    f'➕ 추가 예정: <b>{_format_slot_ranges(_vcur_add_v)}</b></div>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    '<div style="font-size:12px;color:#64748b;background:#f8fafc;'
                    'border:1px solid #e2e8f0;border-radius:6px;padding:6px 10px;margin-bottom:4px;">'
                    '⬅️ 타임라인에서 추가할 시간 슬롯을 클릭해 선택하세요.</div>',
                    unsafe_allow_html=True,
                )
            def_company   = req.get("company_name", ref.get("company_name", ""))
            def_item      = req.get("item_name", "")
            def_loading   = req.get("loading_method", "")
            def_kind_i    = 0 if ref.get("kind") == KIND_IN else 1
            _gate_val     = req.get("gate", ref.get("gate", ""))
            _gate_parts   = _gate_val.split("|", 1) if "|" in _gate_val else [_gate_val, ""]
            def_gate_zone  = _gate_parts[0].strip()
            def_gate_place = _gate_parts[1].strip() if len(_gate_parts) > 1 else ""
            def_ton       = req.get("vehicle_ton", "")
            def_count     = str(req.get("vehicle_count", "1"))
            def_supervisor = req.get("worker_supervisor", "")
            def_guide     = req.get("worker_guide", "")
            def_manager   = req.get("worker_manager", "")
            def_notes     = req.get("notes", "")
            form_key      = f"slot_view_{ref['id'][:8]}"
            conflict      = False
            can_delete    = False
            is_view_only  = True
        else:
            # ── 선택 없음: 시간 선택 배지 ─────────────────────────────────
            is_view_only = False
            sel_in    = sorted(st.session_state.get("sched_sel_in_slots",  []))
            sel_out   = sorted(st.session_state.get("sched_sel_out_slots", []))
            last_kind = st.session_state.get("sched_last_kind", "반입")

            def _badge(slots, kind_label, color, bg, border):
                if not slots:
                    return (
                        f'<div style="font-size:14px;color:{color};background:{bg};'
                        f'border:1px solid {border};border-radius:6px;padding:6px 10px;'
                        f'margin-bottom:4px;">{kind_label}: '
                        f'<span style="color:#94a3b8;">미선택</span></div>'
                    )
                return (
                    f'<div style="font-size:14px;color:{color};background:{bg};'
                    f'border:1px solid {border};border-radius:6px;padding:6px 10px;'
                    f'margin-bottom:4px;">{kind_label}: '
                    f'<b>{current_date.strftime("%Y/%m/%d")}, {_format_slot_ranges(slots)}</b></div>'
                )
            st.markdown(
                _badge(sel_in,  "➡️ 반입", "#2563eb", "#eff6ff", "#bfdbfe") +
                _badge(sel_out, "⬅️ 반출", "#dc2626", "#fff1f2", "#fecaca"),
                unsafe_allow_html=True,
            )

            if last_kind == "반입" and sel_in:
                sel_from, sel_to = _slot_range(sel_in)
                conflict = _has_conflict(sel_in, schedules, KIND_IN)
            elif last_kind == "반출" and sel_out:
                sel_from, sel_to = _slot_range(sel_out)
                conflict = _has_conflict(sel_out, schedules, KIND_OUT)
            else:
                sel_from, sel_to = "08:00", "08:30"
                conflict = False

            if conflict and not is_admin:
                st.markdown(
                    f'<div style="font-size:12px;color:#dc2626;background:#fff1f2;'
                    f'border:1px solid #fecaca;border-radius:6px;padding:4px 10px;'
                    f'margin-bottom:6px;">🔒 선택된 시간대에 이미 예약이 있습니다. 다른 슬롯을 선택하세요.</div>',
                    unsafe_allow_html=True,
                )

            def_company = st.session_state.get("USER_COMPANY", "")
            def_item    = ""
            def_kind_i  = 0 if last_kind == "반입" else 1
            def_gate_zone  = ""
            def_gate_place = ""
            def_ton     = ""
            def_count   = "1"
            def_loading    = ""
            def_supervisor = ""
            def_guide      = ""
            def_manager    = ""
            def_notes   = ""
            # 슬롯 선택이 바뀌면 폼 위젯 기본값도 갱신되도록 key에 시간 포함
            form_key    = f"req_unified_form_{sel_from}_{sel_to}"

        # ── 터미널 옵션 로드 (비활성 제외) ───────────────────────────────────
        try:
            _zone_all      = json.loads(settings_get(con, "gate_zones_json", "[]"))
            _zone_disabled = json.loads(settings_get(con, "gate_zones_disabled_json", "[]"))
            _zone_options  = [z for z in _zone_all if z not in _zone_disabled]
        except Exception:
            _zone_options = []

        # 현재 예약존에서 터미널 선택이 필요한지 확인
        try:
            _terminal_zones = json.loads(settings_get(con, "terminal_zones_json", '["A"]'))
        except Exception:
            _terminal_zones = ["A"]
        _use_terminal = current_zone in _terminal_zones

        # ── 통합 폼 ───────────────────────────────────────────────────────
        with st.form(form_key, clear_on_submit=False):
            company_name = st.text_input("업체명 *", value=def_company,
                                         placeholder="예) OO내장, OO설비")
            _item_idx  = _ITEM_TYPES.index(def_item) if def_item in _ITEM_TYPES else (len(_ITEM_TYPES) - 1 if def_item else 0)
            item_sel   = st.selectbox("자재종류 *", options=_ITEM_TYPES, index=_item_idx)
            item_etc   = st.text_input(
                "기타 자재명 (위에서 '기타' 선택 시 입력)",
                value=(def_item if def_item not in _ITEM_TYPES else ""),
                placeholder="목록에 없는 자재종류를 직접 입력하세요",
            )
            item_name = (item_etc.strip() if item_sel == "기타" and item_etc.strip() else item_sel)

            _load_idx = _LOADING_TYPES.index(def_loading) if def_loading in _LOADING_TYPES else (len(_LOADING_TYPES) - 1 if def_loading else 0)
            loading_sel = st.selectbox("상·하차 방식 *", options=_LOADING_TYPES, index=_load_idx)
            loading_etc = st.text_input(
                "직접입력 (위에서 '직접입력' 선택 시 입력)",
                value=(def_loading if def_loading not in _LOADING_TYPES else ""),
                placeholder="예) 크레인, 호이스트",
            )
            loading_method = (loading_etc.strip() if loading_sel == "직접입력" and loading_etc.strip() else loading_sel)
            st.markdown("---")

            st.markdown("""<style>
            .st-key-vehicle_row .stHorizontalBlock,
            .st-key-worker_row .stHorizontalBlock {
                flex-wrap: nowrap !important;
            }
            .st-key-vehicle_row .stHorizontalBlock > [data-testid="stColumn"],
            .st-key-worker_row .stHorizontalBlock > [data-testid="stColumn"] {
                flex: 1 1 0 !important;
                min-width: 0 !important;
                max-width: none !important;
            }
            </style>""", unsafe_allow_html=True)

            # 터미널 드롭다운 헬퍼 — 점유 중 터미널 제외 (편집 모드 현재값 유지)
            def _terminal_sel(cur_val: str, key_sfx: str = ""):
                _match = cur_val.split("|")[0].strip() if "|" in cur_val else cur_val
                # 점유 중이 아닌 터미널만 표시 (편집 모드 기존 선택값은 예외)
                _avail = [z for z in _zone_options
                          if z not in _occupied_terminals or z == _match]
                _occ_cnt = len(_zone_options) - len(_avail)
                _opts = ["미사용"] + _avail
                _idx  = _opts.index(_match) if _match in _opts else 0
                _label = f"터미널 ({_occ_cnt}개 점유중)" if _occ_cnt else "터미널"
                return st.selectbox(_label, options=_opts, index=_idx,
                                    key=f"terminal_sel{key_sfx}" if key_sfx else None)

            if is_admin_edit or is_view_only:
                new_kind = st.selectbox("구분 *", ["반입", "반출"], index=def_kind_i)
                gate = _terminal_sel(def_gate_zone, "_adm") if _use_terminal else def_gate_zone
            elif is_edit:
                # 일반 사용자 수정: 터미널 존이면 수정 가능, 아니면 유지
                gate = _terminal_sel(def_gate_zone, "_usr") if _use_terminal else def_gate_zone
            else:
                # 신규 신청
                if is_admin:
                    new_kind = last_kind
                    gate = _terminal_sel("", "_new_adm") if _use_terminal else ""
                    admin_req_date = current_date
                    admin_tf = sel_from
                    admin_tt = sel_to
                else:
                    # 일반 사용자: 구분 + 터미널(해당 존만)
                    new_kind = st.selectbox("구분 *", ["반입", "반출"], index=def_kind_i)
                    gate = _terminal_sel("", "_new_usr") if _use_terminal else ""

            with st.container(key="vehicle_row"):
                fv1, fv2 = st.columns(2)
                with fv1:
                    vehicle_ton = st.text_input("차량 규격 *", value=def_ton, placeholder="예) 5톤")
                with fv2:
                    with st.container(key="vehicle_count_wrap"):
                        vehicle_count = st.text_input("차량 대수 *", value=def_count, placeholder="예) 1")

            st.markdown("---")
            worker_supervisor = st.text_input("작업지휘자 *", value=def_supervisor, placeholder="예) 홍길동")
            with st.container(key="worker_row"):
                wr1, wr2 = st.columns(2)
                with wr1:
                    worker_guide   = st.text_input("유도원 *", value=def_guide,   placeholder="예) 홍길동")
                with wr2:
                    worker_manager = st.text_input("담당자 *", value=def_manager, placeholder="예) 홍길동")
            notes        = st.text_input("비고", value=def_notes,
                                         placeholder="예) 파레트 타입 포장, 지게차 양중 시 주의")

            save_extra = False
            if is_edit:
                ca, cb = st.columns(2)
                with ca:
                    with st.container(key="sched_save_btn"):
                        save = st.form_submit_button("저장", type="primary", use_container_width=True)
                with cb:
                    if can_delete:
                        delete = st.form_submit_button("삭제", use_container_width=True)
                    else:
                        delete = False
                        st.markdown(
                            '<div style="font-size:11px;color:#94a3b8;text-align:center;padding-top:10px;">승인됨 — 삭제 불가</div>',
                            unsafe_allow_html=True,
                        )
                submitted = False
            elif is_view_only:
                _vl_f  = admin_sel_list if is_admin else user_sel_list
                _vkf   = _vl_f[0].get("kind", KIND_IN) if _vl_f else KIND_IN
                _vakf  = "sched_sel_in_slots" if _vkf == KIND_IN else "sched_sel_out_slots"
                _vadf  = sorted(st.session_state.get(_vakf, []))
                st.markdown("---")
                with st.container(key="sched_add_slot_btn"):
                    save_extra = st.form_submit_button(
                        "확정", type="primary", use_container_width=True)
                st.markdown(
                    '<div style="text-align:center;color:#64748b;font-size:11px;padding-top:4px;">'
                    '✏️ 내용 수정은 홈 화면 <b>수정</b> 버튼을 이용하세요.</div>',
                    unsafe_allow_html=True,
                )
                save = delete = submitted = False
            else:
                st.markdown("---")
                # 현재 선택 시그니처 계산 — 직전 신청 시그니처와 같으면 "예약 완료" 비활성 표시,
                # 슬롯·날짜·존·구분 중 하나라도 바뀌면 자동으로 "예약 신청" 활성 복귀
                _now_kind_val  = KIND_IN if new_kind == "반입" else KIND_OUT
                _now_slots_key = "sched_sel_in_slots" if _now_kind_val == KIND_IN else "sched_sel_out_slots"
                _now_slots     = tuple(sorted(st.session_state.get(_now_slots_key, [])))
                _now_zone      = st.session_state.get("sched_current_zone", "") or ""
                _now_date      = str(current_date)
                _now_sig       = (_now_kind_val, _now_date, _now_zone, _now_slots)
                _saved_sig     = st.session_state.get("sched_submitted_sig")
                _already_done  = bool(_now_slots) and _saved_sig == _now_sig
                if _saved_sig is not None and not _already_done:
                    st.session_state.pop("sched_submitted_sig", None)
                with st.container(key="sched_submit_btn"):
                    submitted = st.form_submit_button(
                        "✅ 예약 완료" if _already_done else "📋 예약 신청",
                        type="primary",
                        disabled=_already_done,
                        use_container_width=True,
                    )
                save = delete = False

        # ── 추가 슬롯 저장 (뷰 모드 시간 연장) ──────────────────────────────
        if is_view_only and save_extra:
            _vl_s   = admin_sel_list if is_admin else user_sel_list
            _vref_s = _vl_s[0] if _vl_s else {}
            _vkind_s = _vref_s.get("kind", KIND_IN)
            _vadk_s  = "sched_sel_in_slots" if _vkind_s == KIND_IN else "sched_sel_out_slots"
            _vadd_s  = sorted(st.session_state.get(_vadk_s, []))
            if not _vadd_s:
                st.warning("⬅️ 타임라인에서 추가할 시간 슬롯을 먼저 선택해주세요.")
            else:
                n_add = _insert_extra_slots(
                    con, project_id, _vl_s, _vadd_s,
                    _vkind_s,
                    _vref_s.get("gate", ""),
                    _vref_s.get("company_name", ""),
                    _vref_s.get("vehicle_info", ""),
                    user_name,
                )
                st.session_state.pop("sched_sel_in_slots", None)
                st.session_state.pop("sched_sel_out_slots", None)
                if n_add:
                    st.success(f"✅ {n_add}개 슬롯이 추가되었습니다.")
                    st.rerun()
                else:
                    st.warning("추가할 슬롯이 없습니다. (이미 예약된 시간대)")

        # ── 수정 저장 ─────────────────────────────────────────────────────
        if is_edit and save:
            save_errors = []
            if not loading_method.strip():                    save_errors.append("상·하차 방식")
            # 편집 시: 기존 레코드 kind 기준 — 반입만 터미널 필수, 반출은 생략 가능
            _edit_is_in = (ref.get("kind") == KIND_IN) if "ref" in locals() else True
            # 터미널 미사용 허용 — 필수 검사 없음
            if not worker_supervisor.strip():  save_errors.append("작업지휘자")
            if not worker_guide.strip():       save_errors.append("유도원")
            if not worker_manager.strip():     save_errors.append("담당자")
            if save_errors:
                st.error(f"필수 입력 항목을 확인하세요: {', '.join(save_errors)}")
                st.stop()
            final_ton = vehicle_ton.strip()
            if is_admin_edit:
                new_kind_val = KIND_IN if new_kind == "반입" else KIND_OUT
                # 선택된 슬롯에서 req_id 수집
                updated_req_ids = set()
                for sched in sel_list:
                    _rid = sched.get("req_id")
                    if _rid:
                        updated_req_ids.add(_rid)
                # ① requests 테이블 업데이트
                for rid in updated_req_ids:
                    con.table("requests").update({
                        "company_name": company_name.strip(),
                        "item_name": item_name.strip(),
                        "loading_method": loading_method.strip(),
                        "kind": new_kind_val,
                        "gate": gate,
                        "vehicle_ton": final_ton,
                        "vehicle_count": int(vehicle_count or 1),
                        "worker_supervisor": worker_supervisor.strip(),
                        "worker_guide": worker_guide.strip(),
                        "worker_manager": worker_manager.strip(),
                        "notes": notes.strip(),
                        "updated_at": now_str(),
                    }).eq("id", rid).execute()
                # ② 동일 req_id의 모든 schedules 슬롯 일괄 업데이트
                for rid in updated_req_ids:
                    _sids = (con.table("schedules").select("id")
                             .eq("req_id", rid).execute())
                    for _row in (_sids.data or []):
                        schedule_update(con, _row["id"],
                                        company_name=company_name.strip(),
                                        kind=new_kind_val, gate=gate)
                    _audit.log_change(
                        con, project_id=project_id, req_id=rid, action=_audit.EDIT,
                        before_from=_sel_range(sel_list)[0],
                        before_to=_sel_range(sel_list)[1],
                        detail={"by": "admin", "company": company_name.strip(),
                                "item": item_name.strip(), "kind": new_kind_val,
                                "gate": gate},
                    )
                for k in _ADMIN_KEYS:
                    st.session_state.pop(k, None)
                st.session_state.pop("sched_edit_from_home", None)
                # 추가 슬롯 삽입 (관리자 — 타임라인 toggle_book 선택값 사용)
                add_kind_val = KIND_IN if new_kind == "반입" else KIND_OUT
                _add_key2    = "sched_sel_in_slots" if add_kind_val == KIND_IN else "sched_sel_out_slots"
                add_slots2   = sorted(st.session_state.get(_add_key2, []))
                n_added = _insert_extra_slots(con, project_id, sel_list, add_slots2,
                                              add_kind_val, gate, company_name.strip(),
                                              final_ton, user_name)
                st.session_state[_add_key2] = []
                extra_msg = f" + {n_added}개 슬롯 추가" if n_added else ""
                st.success(f"✅ {n}개 슬롯이 수정되었습니다{extra_msg}.")
            else:
                # 일반 사용자 — 본인 예약만 수정 (requester_name 조건)
                rid = ref.get("req_id")
                if rid:
                    # ① requests 테이블 업데이트
                    (con.table("requests").update({
                        "company_name": company_name.strip(),
                        "item_name": item_name.strip(),
                        "loading_method": loading_method.strip(),
                        "gate": gate,
                        "vehicle_ton": final_ton,
                        "vehicle_count": int(vehicle_count or 1),
                        "worker_supervisor": worker_supervisor.strip(),
                        "worker_guide": worker_guide.strip(),
                        "worker_manager": worker_manager.strip(),
                        "notes": notes.strip(),
                        "updated_at": now_str(),
                    }).eq("id", rid).eq("requester_name", user_name).execute())
                    # ② 동일 req_id의 모든 schedules 슬롯 일괄 업데이트
                    _sids2 = (con.table("schedules").select("id")
                              .eq("req_id", rid).execute())
                    for _row in (_sids2.data or []):
                        schedule_update(con, _row["id"], company_name=company_name.strip(), gate=gate)
                # 추가 슬롯 삽입 (일반 사용자)
                add_kind_user = ref.get("kind", KIND_IN)
                _add_key3     = "sched_sel_in_slots" if add_kind_user == KIND_IN else "sched_sel_out_slots"
                add_slots3    = sorted(st.session_state.get(_add_key3, []))
                n_added = _insert_extra_slots(con, project_id, sel_list, add_slots3,
                                              add_kind_user, gate, company_name.strip(),
                                              final_ton, user_name)
                st.session_state[_add_key3] = []
                for k in _USER_KEYS:
                    st.session_state.pop(k, None)
                st.session_state.pop("sched_edit_from_home", None)
                extra_msg = f" + {n_added}개 슬롯 추가" if n_added else ""
                st.success(f"✅ 예약이 수정되었습니다{extra_msg}.")
            st.rerun()

        # ── 삭제 ─────────────────────────────────────────────────────────
        if is_edit and delete:
            if is_admin_edit:
                st.session_state["admin_del_sched"] = [s["id"] for s in sel_list]
            else:
                # 일반 사용자 — 본인 PENDING 예약만 삭제
                from modules.schedule.crud import schedule_delete as _sdel
                _sdel(con, ref["id"])
                rid = ref.get("req_id")
                if rid:
                    (con.table("requests").delete()
                     .eq("id", rid).eq("requester_name", user_name).execute())
                for k in _USER_KEYS:
                    st.session_state.pop(k, None)
                st.session_state.pop("sched_edit_from_home", None)
                st.success("✅ 예약이 취소되었습니다.")
            st.rerun()

        # ── 예약 신청 ─────────────────────────────────────────────────────
        if not is_edit and submitted:
            if conflict and not is_admin:
                st.error("⛔ 선택된 시간대에 이미 예약이 있습니다. 좌측 타임라인에서 빈 슬롯을 선택하세요.")
                st.stop()

            errors = []
            if not company_name.strip():                      errors.append("업체명")
            if not item_name.strip() or item_sel == "기타" and not item_etc.strip():
                errors.append("자재종류")
            if not loading_method.strip() or loading_sel == "직접입력" and not loading_etc.strip():
                errors.append("상·하차 방식")
            # 터미널 미사용 허용 — 필수 검사 없음
            if not vehicle_ton.strip():        errors.append("차량 규격")
            if not worker_supervisor.strip():  errors.append("작업지휘자")
            if not worker_guide.strip():       errors.append("유도원")
            if not worker_manager.strip():     errors.append("담당자")

            if errors:
                st.error(f"필수 입력 항목을 확인하세요: {', '.join(errors)}")
            else:
                final_ton = vehicle_ton.strip()
                kind_val  = KIND_IN if new_kind == "반입" else KIND_OUT
                if is_admin:
                    req_date = str(admin_req_date)
                    req_from = admin_tf
                    req_to   = admin_tt
                else:
                    req_date = str(current_date)
                    req_from = sel_from
                    req_to   = sel_to
                rid = req_insert(con, dict(
                    project_id=project_id,
                    kind=kind_val,
                    company_name=company_name.strip(),
                    item_name=item_name.strip(),
                    loading_method=loading_method.strip(),
                    item_type="", work_type="",
                    date=req_date,
                    time_from=req_from, time_to=req_to,
                    gate=gate,
                    vehicle_type="", vehicle_ton=final_ton,
                    vehicle_count=int(vehicle_count or 1),
                    worker_supervisor=worker_supervisor.strip(),
                    worker_guide=worker_guide.strip(),
                    worker_manager=worker_manager.strip(),
                    notes=notes.strip(),
                    requester_name=st.session_state.get("USER_NAME", ""),
                    requester_role=st.session_state.get("USER_ROLE", ""),
                    requester_username=st.session_state.get("USER_ID", ""),
                    risk_level="MID", sic_training_url="",
                    booking_zone=st.session_state.get("sched_current_zone", "A"),
                ))
                approvals_create_default(con, rid, kind_val)
                _audit.log_change(
                    con, project_id=project_id, req_id=rid, action=_audit.CREATE,
                    after_from=req_from, after_to=req_to,
                    detail={"date": req_date, "company": company_name.strip(),
                            "item": item_name.strip(), "kind": kind_val,
                            "zone": st.session_state.get("sched_current_zone", "A"),
                            "conflict_at_create": bool(conflict)},
                )
                disp = req_display_id(req_get(con, rid) or {"id": rid})
                st.success(f"✅ 예약 신청 완료 ({disp}) — {req_date} {req_from}~{req_to} / {gate}")
                # 슬롯·폼은 그대로 유지하고 시그니처만 저장 → 버튼이 "예약 완료"로 표시됨
                _done_slots = tuple(sorted(
                    st.session_state.get(
                        "sched_sel_in_slots" if kind_val == KIND_IN else "sched_sel_out_slots",
                        [])
                ))
                st.session_state["sched_submitted_sig"] = (
                    kind_val,
                    req_date,
                    st.session_state.get("sched_current_zone", "") or "",
                    _done_slots,
                )
                st.session_state["sched_current_date"] = current_date
                st.rerun()
