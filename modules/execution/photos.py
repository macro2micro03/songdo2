"""Photo capture UI components for execution page."""

from pathlib import Path

import streamlit as st
from supabase import Client

from shared.helpers import bytes_from_camera_or_upload
from modules.execution.crud import photo_add, photos_for_req, photo_delete_slot


MAX_PHOTOS = 4

_PHOTO_CSS = """
<style>
/* 사진 그리드 높이 통일 */
[class*="st-key-photo_del_btn_"] ~ div [data-testid="stImage"] img,
[data-testid="stImage"] img {
    object-fit: cover !important;
}
.photo-grid-cell {
    display: flex;
    flex-direction: column;
    height: 100%;
}

[data-testid="stCameraInput"] video,
[data-testid="stCameraInput"] canvas,
[data-testid="stCameraInput"] img {
    max-width: 720px !important;
    max-height: 540px !important;
    width: 100% !important;
}
[data-testid="stCameraInput"] > div { max-width: 720px !important; margin: 0 auto !important; }
[data-testid="stCameraInput"] [data-testid="stWidgetLabel"],
[data-testid="stCameraInput"] label {
    margin-bottom: 0 !important; padding-bottom: 0 !important; line-height: 1 !important;
}
[data-testid="stCameraInputWebcamComponent"] > div:first-child {
    max-height: 500px !important; overflow: hidden !important;
}
[class*="st-key-photo_del_btn_"] button {
    padding: 0 10px !important; min-height: unset !important; height: 28px !important;
    font-size: 12px !important; border-radius: 4px !important;
    background: #ef4444 !important; border-color: #ef4444 !important;
    color: #ffffff !important; display: inline-flex !important; align-items: center !important;
}
[class*="st-key-photo_del_btn_"] button p { font-size:12px !important; margin:0 !important; color:#ffffff !important; }
[class*="st-key-photo_del_btn_"] button:hover { background:#dc2626 !important; border-color:#dc2626 !important; }
</style>
"""


def ui_photo_upload(con: Client, rid: str):
    """사진 최대 4장 등록 (촬영 또는 파일 업로드).

    카메라 전후면 전환은 모바일 OS의 카메라 UI에 내장된 ↻ 버튼으로 사용자가
    직접 수행합니다. (이전에 facingMode를 JS로 강제하던 hack은 race condition
    으로 깜빡임/불안정을 유발해 제거되었습니다.)
    """
    st.markdown(_PHOTO_CSS, unsafe_allow_html=True)

    existing = photos_for_req(con, rid)
    count = len(existing)

    # ── 등록된 사진 목록 ──────────────────────────────────────────────────
    if existing:
        st.markdown(f"**등록된 사진 ({count}/{MAX_PHOTOS})**")

        # 2열 그리드 — 사진 + 파일명 + 삭제 버튼을 셀 단위로 묶어서 렌더링
        for row_start in range(0, len(existing), 2):
            row_photos = existing[row_start:row_start + 2]
            cols = st.columns(2)
            for col, p in zip(cols, row_photos):
                with col:
                    src = p.get("storage_url") or ""
                    if not src:
                        legacy = p.get("file_path") or ""
                        if legacy and Path(legacy).exists():
                            src = str(legacy)
                    if src:
                        st.image(src, use_container_width=True)
                    else:
                        st.markdown(
                            '<div style="height:160px;background:#f1f5f9;border-radius:6px;'
                            'display:flex;align-items:center;justify-content:center;'
                            'color:#94a3b8;font-size:12px;">파일 없음</div>',
                            unsafe_allow_html=True,
                        )
                    label = p.get('label', '')
                    st.markdown(
                        f'<p style="font-size:11px;color:#64748b;margin:2px 0 4px;'
                        f'overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{label}</p>',
                        unsafe_allow_html=True,
                    )
                    with st.container(key=f"photo_del_btn_{p['id'][:8]}"):
                        if st.button("삭제", key=f"photo_del_{p['id'][:8]}", use_container_width=False):
                            photo_delete_slot(con, rid, p.get("slot_key", ""))
                            st.rerun()

        st.markdown("<div style='margin-bottom:8px'></div>", unsafe_allow_html=True)

    # ── 추가 업로드 (4장 미만일 때만) ────────────────────────────────────
    if count < MAX_PHOTOS:
        remaining = MAX_PHOTOS - count
        st.markdown(f"**사진 추가** (현재 {count}장 · 최대 {remaining}장 더 추가 가능)")
        mode = st.radio("입력 방식", ["직접 촬영", "파일 업로드"], horizontal=True,
                        key=f"photo_mode_{rid}", label_visibility="collapsed")
        if mode == "직접 촬영":
            pic = st.camera_input("카메라로 촬영", key=f"photo_camera_{rid}_{count}")
            st.caption("💡 카메라 전환은 휴대폰 카메라 화면의 ↻ 버튼을 이용하세요.")
            if pic:
                data = bytes_from_camera_or_upload(pic)
                if data:
                    photo_add(con, rid, f"photo_{count + 1}", f"사진 {count + 1}", data, ".jpg")
                    st.rerun()
        else:
            uploads = st.file_uploader(
                f"사진 선택 (최대 {remaining}장, 복수 선택 가능)",
                type=["jpg", "jpeg", "png"],
                accept_multiple_files=True,
                key=f"photo_upload_{rid}_{count}",
            )
            if uploads:
                saved = 0
                for i, upl in enumerate(uploads[:remaining]):
                    data = bytes_from_camera_or_upload(upl)
                    if data:
                        photo_add(con, rid, f"photo_{count + i + 1}", upl.name, data, ".jpg")
                        saved += 1
                if saved:
                    st.rerun()
    else:
        st.info(f"사진 {MAX_PHOTOS}장이 모두 등록되었습니다. 삭제 후 다시 추가할 수 있습니다.")


# 하위 호환성 유지
def ui_photo_capture_required(con: Client, rid: str):
    ui_photo_upload(con, rid)


def ui_photo_optional_upload(con: Client, rid: str):
    pass
