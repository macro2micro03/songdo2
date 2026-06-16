"""PDF generation functions."""

from pathlib import Path
from typing import Dict, Any, List, Optional
from urllib.parse import unquote

from supabase import Client

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

try:
    from reportlab.lib.utils import ImageReader
except Exception:
    pass

# 한글 폰트 등록 — 번들 NanumGothic 우선, OS별 fallback
import os
import logging

logger = logging.getLogger(__name__)

KOREAN_FONT_REGISTERED = False
KOREAN_FONT_DIAG: Dict[str, Any] = {
    "normal_path": None,
    "bold_path": None,
    "errors": [],
    "bundle_dir": None,
    "bundle_dir_exists": False,
    "bundle_dir_contents": [],
}

_FONT_NORMAL = "Helvetica"
_FONT_BOLD   = "Helvetica-Bold"

_BUNDLE_DIR = os.path.join(os.path.dirname(__file__), "fonts")
KOREAN_FONT_DIAG["bundle_dir"] = _BUNDLE_DIR
KOREAN_FONT_DIAG["bundle_dir_exists"] = os.path.isdir(_BUNDLE_DIR)
if KOREAN_FONT_DIAG["bundle_dir_exists"]:
    try:
        KOREAN_FONT_DIAG["bundle_dir_contents"] = os.listdir(_BUNDLE_DIR)
    except Exception as _e:
        KOREAN_FONT_DIAG["errors"].append(f"listdir({_BUNDLE_DIR}): {_e}")

_candidates_normal = [
    os.path.join(_BUNDLE_DIR, "NanumGothic.ttf"),       # 번들 (Cloud/Linux 최우선)
    "C:/Windows/Fonts/malgun.ttf",                      # Windows 로컬
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",  # Linux apt
    "/usr/share/fonts/nanum/NanumGothic.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
]
_candidates_bold = [
    os.path.join(_BUNDLE_DIR, "NanumGothicBold.ttf"),
    "C:/Windows/Fonts/malgunbd.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
    "/usr/share/fonts/nanum/NanumGothicBold.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
]

for _p in _candidates_normal:
    if not os.path.exists(_p):
        continue
    try:
        sz = os.path.getsize(_p)
        if sz < 100_000:
            KOREAN_FONT_DIAG["errors"].append(f"{_p}: file too small ({sz}B)")
            continue
        pdfmetrics.registerFont(TTFont("KoreanFont", _p))
        _FONT_NORMAL = "KoreanFont"
        KOREAN_FONT_DIAG["normal_path"] = _p
        KOREAN_FONT_REGISTERED = True
        logger.info(f"[PDF] Korean font (normal) registered: {_p} ({sz}B)")
        break
    except Exception as _e:
        KOREAN_FONT_DIAG["errors"].append(f"register({_p}): {_e}")
        logger.warning(f"[PDF] Failed to register {_p}: {_e}")

for _p in _candidates_bold:
    if not os.path.exists(_p):
        continue
    try:
        sz = os.path.getsize(_p)
        if sz < 100_000:
            KOREAN_FONT_DIAG["errors"].append(f"{_p}: file too small ({sz}B)")
            continue
        pdfmetrics.registerFont(TTFont("KoreanFont-Bold", _p))
        _FONT_BOLD = "KoreanFont-Bold"
        KOREAN_FONT_DIAG["bold_path"] = _p
        logger.info(f"[PDF] Korean font (bold) registered: {_p} ({sz}B)")
        break
    except Exception as _e:
        KOREAN_FONT_DIAG["errors"].append(f"register_bold({_p}): {_e}")
        logger.warning(f"[PDF] Failed to register bold {_p}: {_e}")

if not KOREAN_FONT_REGISTERED:
    logger.error(
        f"[PDF] ⚠️ Korean font NOT registered! "
        f"BUNDLE_DIR={_BUNDLE_DIR} "
        f"exists={KOREAN_FONT_DIAG['bundle_dir_exists']} "
        f"contents={KOREAN_FONT_DIAG['bundle_dir_contents']} "
        f"errors={KOREAN_FONT_DIAG['errors']}"
    )

QR_AVAILABLE = True
try:
    import qrcode
except Exception:
    QR_AVAILABLE = False

from shared.helpers import now_str
from shared.storage import cache_to_local
from db.connection import photos_bucket
from config import KIND_IN, CHECK_ITEMS, APP_VERSION
from modules.execution.crud import final_approved_signs


def _resolve_image(con: Client, value: str) -> Optional[Path]:
    """Resolve an image reference to a local path that ImageReader can read.

    ``value`` may be a local file path, a Supabase Storage object key (e.g.
    ``<rid>/photo_1_xxx.jpg``), or a public Storage URL. The function downloads
    from Storage on demand and caches under BASE_DIR/tmp_cache.
    """
    if not value:
        return None
    s = str(value)

    if s.startswith("http://") or s.startswith("https://"):
        marker = "/object/public/"
        if marker in s:
            tail = s.split(marker, 1)[1]
            bucket, _, obj = tail.partition("/")
            return cache_to_local(con, bucket, unquote(obj.split("?")[0]))
        marker = "/object/sign/"
        if marker in s:
            tail = s.split(marker, 1)[1]
            bucket, _, obj = tail.partition("/")
            return cache_to_local(con, bucket, unquote(obj.split("?")[0]))
        return None

    p = Path(s)
    if p.exists() and p.stat().st_size > 0:
        return p

    # Treat as a Supabase Storage object key in the photos bucket
    return cache_to_local(con, photos_bucket(), s)


def qr_generate_png(url: str, out_path: Path) -> Optional[Path]:
    """Generate a QR code PNG from a URL."""
    if not QR_AVAILABLE:
        return None
    qrcode.make(url).save(out_path)
    return out_path


def pdf_simple_header(c: canvas.Canvas, title: str, subtitle: str = "") -> None:
    """Draw a simple header on a PDF page."""
    c.setFont(_FONT_BOLD, 16)
    c.drawString(20 * mm, 287 * mm, title)
    if subtitle:
        c.setFont(_FONT_NORMAL, 10)
        c.drawString(20 * mm, 281 * mm, subtitle)
    c.line(20 * mm, 278 * mm, 190 * mm, 278 * mm)


def draw_signatures(c: canvas.Canvas, signs: List[Dict[str, Any]], y_mm: float,
                    con: Optional[Client] = None) -> None:
    """Draw signature images on a PDF page."""
    if not signs:
        c.setFont(_FONT_NORMAL, 9)
        c.drawString(20 * mm, y_mm * mm, "서명 없음")
        return
    x = 20 * mm
    y = y_mm * mm
    for s in signs:
        c.setFont(_FONT_NORMAL, 9)
        c.drawString(x, y + 18, f"{s.get('role_required', '')} / {s.get('signer_name', '')}")
        c.drawString(x, y + 10, f"{s.get('signed_at', '')}")
        sign_local = _resolve_image(con, s.get("sign_png_path") or "") if con else None
        if sign_local:
            try:
                c.drawImage(
                    ImageReader(str(sign_local)),
                    x, y - 6,
                    width=28 * mm, height=12 * mm,
                    preserveAspectRatio=True, mask="auto",
                )
            except Exception:
                pass
        else:
            # 서명 미사용: 이름 정자 표기
            c.setFont(_FONT_NORMAL, 9)
            c.drawString(x, y - 2, f"(정자) {s.get('signer_name', '')}")
        stamp_local = _resolve_image(con, s.get("stamp_png_path") or "") if con else None
        if stamp_local:
            try:
                c.drawImage(
                    ImageReader(str(stamp_local)),
                    x + 32 * mm, y - 6,
                    width=14 * mm, height=14 * mm,
                    preserveAspectRatio=True, mask="auto",
                )
            except Exception:
                pass
        x += 60 * mm


def pdf_plan(
    con: Client,
    req: Dict[str, Any],
    approvals: List[Dict[str, Any]],
    out_path: Path,
    photos: Optional[List[Dict[str, Any]]] = None,
) -> Path:
    """Generate the plan PDF (자재 반출입 계획서)."""
    c = canvas.Canvas(str(out_path), pagesize=A4)
    pdf_simple_header(
        c,
        "자재반입계획서" if req['kind'] == KIND_IN else "자재반출 사진대지",
        f"생성: {now_str()} · {APP_VERSION}",
    )
    y = 270 * mm
    c.setFont(_FONT_NORMAL, 10)
    # gate 파싱
    gate_raw = req.get("gate", "")
    if "|" in gate_raw:
        _gp = gate_raw.split("|", 1)
        gate_disp = f"{_gp[0].strip()} / {_gp[1].strip()}"
    else:
        gate_disp = gate_raw

    # 차량 표시: 5톤(2대)
    vton = req.get("vehicle_ton", "")
    vcnt = req.get("vehicle_count", "")
    vehicle_disp = f"{vton}({vcnt}대)" if vton and vcnt else f"{vton}{vcnt}"

    kind_txt = "반입" if req["kind"] == KIND_IN else "반출"

    # 하역존 + 저장 기간
    zone_disp = req.get("booking_zone", "") or "-"
    _ss = (req.get("store_start") or "")[:10]
    _se = (req.get("store_end") or "")[:10]
    if _ss and _se:
        store_period = f"{_ss} ~ {_se}"
    elif req.get("date"):
        try:
            from shared.storage_plan import default_days as _sd, add_days as _ad
            _d = req["date"][:10]
            store_period = f"{_d} ~ {_ad(_d, _sd(con))} (기본)"
        except Exception:
            store_period = "-"
    else:
        store_period = "-"

    fields = [
        ("회사명",          req.get("company_name", "")),
        (f"반입/반출 자재", req.get("item_name", "")),
        ("상·하차 방식",    req.get("loading_method", "")),
        ("요청자",          f"{req.get('requester_name', '').replace('/', ' ')} ({req.get('requester_role', '')})"),
        ("일자",            req.get("date", "")),
        ("시간",            f"{req.get('time_from', '')} ~ {req.get('time_to', '')}"),
        ("하역존",          zone_disp),
        ("저장 터미널",     gate_disp),
        ("저장 기간",       store_period),
        ("운반 차량",       vehicle_disp),
        ("작업지휘자",      req.get("worker_supervisor", "")),
        ("유도원",          req.get("worker_guide", "")),
        ("담당자",          req.get("worker_manager", "")),
        ("비고",            req.get("notes", "")),
    ]
    for k, v in fields:
        c.drawString(20 * mm, y, f"{k}: {v}")
        y -= 7 * mm
    y -= 4 * mm
    c.setFont(_FONT_BOLD, 11)
    c.drawString(20 * mm, y, "확정 이력")
    y -= 7 * mm
    c.setFont(_FONT_NORMAL, 10)
    for ap in approvals:
        txt = f"{ap['step_no']}. {ap['role_required']} - {ap['status']}"
        if ap["status"] == "APPROVED":
            txt += f" · {ap.get('signer_name', '')} · {ap.get('signed_at', '')}"
        if ap["status"] == "REJECTED":
            txt += f" · 사유: {ap.get('reject_reason', '')}"
        c.drawString(22 * mm, y, txt)
        y -= 6 * mm
    # 우측 하단 서명
    sign_x = 150 * mm
    c.setFont(_FONT_BOLD, 11)
    c.drawString(sign_x, 42 * mm, "최종 확정 서명")
    approved = [a for a in approvals if a.get("status") == "APPROVED"]
    x = sign_x
    y = 22 * mm
    for s in approved:
        c.setFont(_FONT_NORMAL, 9)
        c.drawString(x, y + 18, f"{s.get('role_required', '')} / {s.get('signer_name', '')}")
        c.drawString(x, y + 10, f"{s.get('signed_at', '')}")
        sign_local = _resolve_image(con, s.get("sign_png_path") or "")
        if sign_local:
            try:
                c.drawImage(
                    ImageReader(str(sign_local)),
                    x, y - 6,
                    width=28 * mm, height=12 * mm,
                    preserveAspectRatio=True, mask="auto",
                )
            except Exception:
                pass
        else:
            c.setFont(_FONT_NORMAL, 9)
            c.drawString(x, y - 2, f"(정자) {s.get('signer_name', '')}")
        x += 60 * mm
    c.showPage()

    # ── 사진대지 (2×2 표 형태, 가로 페이지) ─────────────────────────
    if photos:
        resolved = []
        for p in photos:
            local = _resolve_image(con, p.get("storage_url") or p.get("file_path") or "")
            if local:
                resolved.append((p, local))
        valid = resolved
        from reportlab.lib.pagesizes import landscape
        pw, ph = landscape(A4)   # 가로: 297mm, 세로: 210mm
        margin_x = 12 * mm
        margin_y = 12 * mm
        gap = 5 * mm
        label_h = 8 * mm
        header_h = 14 * mm
        col_w = (pw - margin_x * 2 - gap) / 2
        img_h = (ph - margin_y * 2 - header_h - gap - label_h * 2 - gap * 2) / 2

        def cell_pos(row, col):
            x = margin_x + col * (col_w + gap)
            y = ph - margin_y - header_h - row * (img_h + label_h + gap) - img_h
            return x, y

        for page_start in range(0, len(valid), 4):
            c.setPageSize((pw, ph))
            c.setFont(_FONT_BOLD, 12)
            c.drawString(margin_x, ph - 10 * mm, "사진대지")
            c.line(margin_x, ph - 12 * mm, pw - margin_x, ph - 12 * mm)

            batch = valid[page_start:page_start + 4]
            for i, item in enumerate(batch):
                photo, local_path = item
                row, col = divmod(i, 2)
                px, py = cell_pos(row, col)
                label = f"[{photo.get('slot_key', '')}] {photo.get('label', '')}"

                c.setStrokeColorRGB(0.6, 0.6, 0.6)
                c.rect(px, py - label_h, col_w, img_h + label_h)
                c.line(px, py, px + col_w, py)

                pad = 2 * mm
                try:
                    c.drawImage(
                        ImageReader(str(local_path)),
                        px + pad, py + pad,
                        width=col_w - pad * 2,
                        height=img_h - pad * 2,
                        preserveAspectRatio=True,
                        anchor='c',
                        mask="auto",
                    )
                except Exception:
                    c.setFont(_FONT_NORMAL, 9)
                    c.drawCentredString(px + col_w / 2, py + img_h / 2, "(사진 로드 실패)")

                c.setFont(_FONT_NORMAL, 8)
                c.setFillColorRGB(0, 0, 0)
                c.drawCentredString(px + col_w / 2, py - label_h + 2 * mm, label)

            c.showPage()

    c.save()
    return out_path


def pdf_permit(
    con: Client,
    req: Dict[str, Any],
    sic_url: str,
    qr_path: Optional[Path],
    out_path: Path,
) -> Path:
    """Generate the permit PDF (자재 차량 진출입 허가증)."""
    c = canvas.Canvas(str(out_path), pagesize=A4)
    pdf_simple_header(c, "자재 차량 진출입 허가증", f"생성: {now_str()} · {APP_VERSION}")
    c.setFont(_FONT_NORMAL, 11)
    c.drawString(20 * mm, 260 * mm, f"입고 회사명: {req.get('company_name', '')}")
    c.drawString(20 * mm, 252 * mm, f"운전원: {req.get('driver_name', '')} / {req.get('driver_phone', '')}")
    c.drawString(
        20 * mm, 244 * mm,
        f"사용 GATE: {req.get('gate', '')} · 일시: {req.get('date', '')} {req.get('time_from', '')}~{req.get('time_to', '')}",
    )
    c.setFont(_FONT_BOLD, 11)
    c.drawString(20 * mm, 232 * mm, "필수 준수사항")
    c.setFont(_FONT_NORMAL, 10)
    rules = [
        "1. 하차 시 안전모 착용",
        "2. 운전석 유리창 개방 필수",
        "3. 현장 내 속도 10km/h 이내 주행",
        "4. 비상등 상시 점등",
        "5. 주정차 시 고임목 설치",
        "6. 유도원 통제하에 운영",
    ]
    y = 225 * mm
    for r in rules:
        c.drawString(22 * mm, y, r)
        y -= 6 * mm
    c.setFont(_FONT_BOLD, 11)
    c.drawString(20 * mm, 180 * mm, "방문자교육(QR)")
    c.setFont(_FONT_NORMAL, 9)
    c.drawString(20 * mm, 174 * mm, f"URL: {sic_url}")
    if qr_path and qr_path.exists():
        try:
            c.drawImage(
                ImageReader(str(qr_path)),
                20 * mm, 125 * mm,
                width=45 * mm, height=45 * mm,
                preserveAspectRatio=True, mask="auto",
            )
        except Exception:
            c.drawString(20 * mm, 160 * mm, "(QR 삽입 실패)")
    c.setFont(_FONT_BOLD, 11)
    c.drawString(80 * mm, 145 * mm, "담당자 승인")
    draw_signatures(c, final_approved_signs(con, req["id"])[-1:], 122, con=con)
    c.showPage()
    c.save()
    return out_path


def pdf_check_card(
    con: Client,
    req: Dict[str, Any],
    check_json: Dict[str, Any],
    out_path: Path,
) -> Path:
    """Generate the check card PDF (자재 상/하차 점검카드)."""
    c = canvas.Canvas(str(out_path), pagesize=A4)
    pdf_simple_header(c, "자재 상/하차 점검카드", f"요청ID: {req['id']} · 생성: {now_str()} · {APP_VERSION}")
    c.setFont(_FONT_NORMAL, 10)
    c.drawString(20 * mm, 270 * mm, f"협력회사: {req.get('company_name', '')}")
    c.drawString(20 * mm, 262 * mm, f"화물/자재: {req.get('item_name', '')} / 종류: {req.get('item_type', '')}")
    c.drawString(
        20 * mm, 254 * mm,
        f"일시: {req.get('date', '')} {req.get('time_from', '')}~{req.get('time_to', '')} / GATE: {req.get('gate', '')}",
    )
    y = 240 * mm
    for key, title in CHECK_ITEMS:
        val = "✓" if check_json.get(key) else "✗"
        c.drawString(20 * mm, y, f"{title}: {val}")
        y -= 7 * mm
        if y < 20 * mm:
            c.showPage()
            y = 270 * mm
    c.showPage()
    c.save()
    return out_path


def pdf_exec_summary(
    con: Client,
    req: Dict[str, Any],
    photos: List[Dict[str, Any]],
    out_path: Path,
) -> Path:
    """Generate the execution summary PDF (실행 기록/사진 요약)."""
    c = canvas.Canvas(str(out_path), pagesize=A4)
    pdf_simple_header(c, "실행 기록(사진 요약)", f"요청ID: {req['id']} · 생성: {now_str()} · {APP_VERSION}")
    c.setFont(_FONT_NORMAL, 10)
    y = 270 * mm
    c.drawString(
        20 * mm, y,
        f"회사: {req.get('company_name', '')} / 자재: {req.get('item_name', '')} / {'반입' if req['kind'] == KIND_IN else '반출'}",
    )
    y -= 8 * mm
    c.drawString(
        20 * mm, y,
        f"일시: {req.get('date', '')} {req.get('time_from', '')}~{req.get('time_to', '')} / GATE: {req.get('gate', '')}",
    )
    y -= 12 * mm
    c.setFont(_FONT_BOLD, 11)
    c.drawString(20 * mm, y, "사진 목록")
    y -= 8 * mm
    c.setFont(_FONT_NORMAL, 10)
    for p in photos:
        fname = Path(p.get("file_path") or p.get("storage_url") or "").name
        c.drawString(22 * mm, y, f"- [{p.get('slot_key', '')}] {p.get('label', '')} · {fname}")
        y -= 6 * mm
        if y < 20 * mm:
            c.showPage()
            y = 270 * mm
    c.showPage()
    c.save()
    return out_path
