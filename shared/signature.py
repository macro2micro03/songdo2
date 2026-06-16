"""Signature and stamp capture UI components."""

import uuid
from pathlib import Path
from typing import Optional, Tuple

import streamlit as st

from db.connection import get_supabase, path_output
from shared.helpers import bytes_from_camera_or_upload, png_bytes_from_canvas_rgba
from shared.storage import upload_output

CANVAS_AVAILABLE = True
try:
    from streamlit_drawable_canvas import st_canvas
except Exception:
    CANVAS_AVAILABLE = False


def save_bytes_to_file(folder_key: str, rid: str, tag: str, data: bytes, suffix: str) -> str:
    """Persist raw bytes for a request artifact.

    Writes a local copy under MaterialToolShared/<folder_key>/ for in-session display
    and uploads the same bytes to the Supabase outputs bucket. Returns the Supabase
    Storage object key (e.g. ``sign/<rid>_xxx.png``) so it can be stored on a row
    and later resolved via :func:`shared.storage.cache_to_local`.
    """
    out = path_output()[folder_key]
    fname = f"{rid}_{tag}_{uuid.uuid4().hex[:8]}{suffix}"
    fp = out / fname
    fp.write_bytes(data)
    try:
        sb = get_supabase()
        return upload_output(sb, folder_key, rid, suffix, data, unique=True) or str(fp)
    except Exception:
        return str(fp)


def ui_signature_block(rid: str, label: str, key_prefix: str) -> Tuple[Optional[str], Optional[str]]:
    """Render signature + stamp upload block. Returns (sign_path, stamp_path)."""
    st.markdown(f"#### {label}")
    st.markdown("""
    <style>
    [class*="_sign_img_wrap"] [data-testid="stImage"] {
        display: block !important;
        margin: 0 auto !important;
        text-align: center !important;
    }
    [class*="_sign_img_wrap"] [data-testid="stImage"] img {
        display: block !important;
        margin: 0 auto !important;
    }
    /* 캔버스 iframe 가운데 정렬 — 부모 구조 무관하게 블록 margin:auto 방식 */
    [class*="_canvas_outer"] iframe {
        display: block !important;
        width: 300px !important;
        margin-left: auto !important;
        margin-right: auto !important;
    }
    @media (max-width: 480px) {
        /* 서명저장/Clear 버튼 행: 2열 유지 (특이도 0,3,0 — 전역 스택킹 규칙과 동일, 나중 선언 우선) */
        [class*="_btn_row"] [data-testid="stHorizontalBlock"] {
            flex-wrap: nowrap !important;
        }
        [class*="_btn_row"] [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
            flex: 0 0 50% !important;
            min-width: 0 !important;
            max-width: 50% !important;
        }
        /* 서명 미리보기 행: 스택 해제 */
        [class*="_sign_preview_row"] [data-testid="stHorizontalBlock"] {
            flex-wrap: nowrap !important;
        }
        [class*="_sign_preview_row"] [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:first-child {
            flex: 1 1 auto !important;
            min-width: 0 !important;
        }
        [class*="_sign_preview_row"] [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:last-child {
            flex: 0 0 auto !important;
        }
    }
    [class*="_sign_change"] button,
    [class*="_stamp_change"] button {
        min-height: 22px !important;
        height: 22px !important;
        padding: 0 8px !important;
        font-size: 12px !important;
        background-color: #6b7280 !important;
        border-color: #6b7280 !important;
        color: #ffffff !important;
    }
    [class*="_sign_change"] button p,
    [class*="_stamp_change"] button p {
        line-height: 22px !important;
        margin: 0 !important;
        font-size: 12px !important;
        color: #ffffff !important;
    }
    [class*="_sign_change"] button:hover,
    [class*="_stamp_change"] button:hover {
        background-color: #4b5563 !important;
        border-color: #4b5563 !important;
    }
    [class*="_save"] button {
        min-height: 44px !important;
        height: 44px !important;
        min-height: 44px !important;
        padding: 0 !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%) !important;
        border-color: #2563eb !important;
        color: #ffffff !important;
    }
    [class*="_save"] button p {
        line-height: 1 !important;
        margin: 0 !important;
        padding: 0 !important;
        color: #ffffff !important;
    }
    [class*="_save"] button:hover {
        background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%) !important;
        border-color: #1e40af !important;
    }
    [class*="_clear"] button {
        min-height: 44px !important;
        height: 44px !important;
        padding: 0 !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
    }
    [class*="_clear"] button p {
        line-height: 1 !important;
        margin: 0 !important;
        padding: 0 !important;
    }
    /* 서명 저장 완료 알림 박스 */
    [data-testid="stAlert"] {
        width: 60% !important;
        min-width: 200px !important;
        max-width: 400px !important;
        margin-left: auto !important;
        margin-right: auto !important;
        padding: 8px 12px !important;
        min-height: unset !important;
        box-sizing: border-box !important;
        position: relative !important;
    }
    /* 내부 컨테이너: 상대 위치 기준 */
    [data-testid="stAlert"] > div,
    [data-testid="stAlert"] [data-testid="stAlertContainer"] {
        display: flex !important;
        align-items: center !important;
        width: 100% !important;
        position: relative !important;
    }
    /* 아이콘: absolute로 왼쪽에 고정 → 텍스트 흐름에서 제외 */
    [data-testid="stAlert"] svg {
        position: absolute !important;
        left: 0 !important;
        top: 50% !important;
        transform: translateY(-50%) !important;
        flex-shrink: 0 !important;
    }
    /* 텍스트 컨테이너: 박스 전체 너비 사용 → 진짜 가운데 */
    [data-testid="stAlert"] [data-testid="stMarkdownContainer"] {
        flex: 1 !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
    }
    [data-testid="stAlert"] [data-testid="stMarkdownContainer"] p {
        font-size: 13px !important;
        line-height: 1 !important;
        margin: 0 !important;
        padding: 0 !important;
        text-align: center !important;
        transform: translateY(-8px) !important;
    }
</style>
    """, unsafe_allow_html=True)
    sign_path = None
    stamp_path = None
    mode = st.radio("서명 방식", ["직접 서명(권장)", "이미지 업로드(옵션)"], horizontal=True, key=f"{key_prefix}_mode")
    if mode == "직접 서명(권장)":
        if not CANVAS_AVAILABLE:
            st.warning("streamlit-drawable-canvas, pillow 설치 필요")
        else:
            st.caption("손가락/펜으로 서명하세요. (지우기: Clear)")
            with st.container(key=f"{key_prefix}_canvas_outer"):
                canvas_res = st_canvas(
                    fill_color="rgba(255, 255, 255, 0)",
                    stroke_width=4,
                    stroke_color="#111111",
                    background_color="#ffffff",
                    height=180,
                    width=300,
                    drawing_mode="freedraw",
                    key=f"{key_prefix}_canvas",
                )
            st.markdown("<div style='margin-top:16px'></div>", unsafe_allow_html=True)
            with st.container(key=f"{key_prefix}_btn_row"):
                colA, colB = st.columns(2, gap="small")
            with colA:
                if st.button("서명 저장", key=f"{key_prefix}_save", use_container_width=True):
                    if canvas_res.image_data is None:
                        st.session_state[f"{key_prefix}_save_msg"] = ("error", "서명이 없습니다.")
                    else:
                        png = png_bytes_from_canvas_rgba(canvas_res.image_data)
                        if not png:
                            st.session_state[f"{key_prefix}_save_msg"] = ("error", "서명 저장 실패")
                        else:
                            sign_path = save_bytes_to_file("sign", rid, "sign_draw", png, ".png")
                            st.session_state[f"{key_prefix}_sign_path"] = sign_path
                            st.session_state[f"{key_prefix}_save_msg"] = ("success", "서명 저장 완료")
            with colB:
                if st.button("Clear", key=f"{key_prefix}_clear", use_container_width=True):
                    st.session_state.pop(f"{key_prefix}_save_msg", None)
            # 알림 박스: 컬럼 바깥 전체 너비에서 렌더링
            _msg = st.session_state.get(f"{key_prefix}_save_msg")
            if _msg:
                if _msg[0] == "success":
                    st.success(_msg[1])
                else:
                    st.error(_msg[1])
            if sign_path:
                st.session_state[f"{key_prefix}_sign_path"] = sign_path
            sign_path = st.session_state.get(f"{key_prefix}_sign_path", None)
    else:
        sign_preview = st.session_state.get(f"{key_prefix}_sign_preview")
        if sign_preview and not st.session_state.get(f"{key_prefix}_sign_editing"):
            import base64
            b64 = base64.b64encode(sign_preview["data"]).decode()
            st.markdown(
                f"<div style='text-align:center;'>"
                f"<img src='data:image/png;base64,{b64}' width='200' style='display:inline-block;'/>"
                f"<div style='font-size:12px;color:#666;margin-top:1px;margin-bottom:12px;'>{sign_preview['name']}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )
            col_l, col_m, col_r = st.columns([2, 1, 2])
            with col_m:
                if st.button("변경", key=f"{key_prefix}_sign_change", use_container_width=True):
                    st.session_state[f"{key_prefix}_sign_editing"] = True
                    st.rerun()
            sign_path = st.session_state.get(f"{key_prefix}_sign_path")
        else:
            upl = st.file_uploader("서명 이미지 업로드(PNG/JPG)", type=["png", "jpg", "jpeg"], key=f"{key_prefix}_sign_upload")
            if upl:
                data = bytes_from_camera_or_upload(upl)
                if data:
                    suffix = Path(upl.name).suffix.lower() or ".png"
                    sign_path = save_bytes_to_file("sign", rid, "sign_upl", data, suffix)
                    st.session_state[f"{key_prefix}_sign_path"] = sign_path
                    st.session_state[f"{key_prefix}_sign_preview"] = {"data": data, "name": upl.name}
                    st.session_state[f"{key_prefix}_sign_editing"] = False
                    st.rerun()

    stamp_path = st.session_state.get(f"{key_prefix}_stamp_path", None)
    return sign_path, stamp_path
