"""Shared utility functions used across modules."""
import hashlib
import base64
import uuid
from datetime import datetime, date
from pathlib import Path
from typing import Optional
import numpy as np

def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def today_str() -> str:
    return date.today().isoformat()

def ensure_dir(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p

def file_sha1(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()

def b64_download_link(file_path: Path, label: str) -> str:
    data = file_path.read_bytes()
    b64 = base64.b64encode(data).decode()
    return f'<a href="data:application/octet-stream;base64,{b64}" download="{file_path.name}">{label}</a>'

def b64_pdf_preview(file_path: Path) -> str:
    data = file_path.read_bytes()
    b64 = base64.b64encode(data).decode()
    uid = uuid.uuid4().hex[:8]
    return f"""
<div id="pdfwrap_{uid}" style="width:100%;height:620px;border:1px solid #e2e8f0;border-radius:8px;overflow:hidden;">
  <iframe id="pdfiframe_{uid}" width="100%" height="100%" style="border:none;"></iframe>
</div>
<script>
(function(){{
  var b64 = "{b64}";
  var bin = atob(b64);
  var arr = new Uint8Array(bin.length);
  for(var i=0;i<bin.length;i++) arr[i]=bin.charCodeAt(i);
  var blob = new Blob([arr],{{type:"application/pdf"}});
  var url = URL.createObjectURL(blob);
  document.getElementById("pdfiframe_{uid}").src = url;
}})();
</script>
"""

def bytes_from_camera_or_upload(upl) -> Optional[bytes]:
    if upl is None:
        return None
    raw = upl.read() if hasattr(upl, "read") else upl
    if isinstance(raw, (bytes, bytearray)):
        return bytes(raw)
    return None

def png_bytes_from_canvas_rgba(canvas_rgba) -> Optional[bytes]:
    if canvas_rgba is None:
        return None
    try:
        arr = np.array(canvas_rgba)
        if arr.ndim == 3 and arr.shape[2] == 4:
            alpha = arr[:, :, 3]
            if alpha.max() == 0:
                return None
        from PIL import Image
        import io
        img = Image.fromarray(arr.astype("uint8"), "RGBA")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception:
        return None

def new_id() -> str:
    return uuid.uuid4().hex

def format_phone(raw: str) -> str:
    """숫자만 추출해서 000-0000-0000 형태로 반환."""
    digits = ''.join(c for c in raw if c.isdigit())[:11]
    if len(digits) == 11:
        return f"{digits[:3]}-{digits[3:7]}-{digits[7:]}"
    if len(digits) == 10:
        return f"{digits[:3]}-{digits[3:6]}-{digits[6:]}"
    return digits


def phone_input(label: str, key: str, value: str = "", placeholder: str = "숫자만 (-제외)"):
    """자동 하이픈 포맷팅 전화번호 입력 위젯 (폼 외부 전용)."""
    import streamlit as st

    def _on_change():
        st.session_state[key] = format_phone(st.session_state.get(key, ""))

    if key not in st.session_state:
        st.session_state[key] = format_phone(value) if value else ""

    st.text_input(label, key=key, placeholder=placeholder, on_change=_on_change)
    return st.session_state.get(key, "")


def req_display_id(r: dict) -> str:
    """Return display ID in YYMMDD-N format based on planned date (e.g. 260410-1)."""
    planned = (r.get('date') or r.get('created_at') or '')[:10]  # "2026-04-10"
    if len(planned) < 10:
        return (r.get('id') or '')[:8]
    yymmdd = planned[2:4] + planned[5:7] + planned[8:10]
    seq = r.get('day_seq', 0)
    return f"{yymmdd}-{seq}"
