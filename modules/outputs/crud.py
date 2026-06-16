"""Outputs CRUD operations and generation."""

import json
import zipfile
from pathlib import Path
from typing import Dict, Any, List, Optional

from supabase import Client
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm

from shared.helpers import now_str, req_display_id
from shared.storage import upload_output
from db.models import settings_get
from db.connection import path_output, path_output_root
from config import APP_VERSION
from modules.request.crud import req_get
from modules.approval.crud import approvals_for_req
from modules.execution.crud import execution_get, photos_for_req
from modules.outputs.pdf import (
    QR_AVAILABLE,
    qr_generate_png,
    pdf_simple_header,
    pdf_plan,
    pdf_permit,
    pdf_check_card,
    pdf_exec_summary,
)


def _upload_artifact(con: Client, kind: str, rid: str, local: Optional[Path]) -> str:
    """Upload a generated artifact to the outputs bucket. Returns the storage path
    (relative to the bucket), or empty string if upload skipped/failed."""
    if not local:
        return ""
    try:
        local_path = Path(local)
        if not local_path.exists() or local_path.stat().st_size == 0:
            return ""
        data = local_path.read_bytes()
        return upload_output(con, kind, rid, local_path.suffix, data)
    except Exception:
        return ""


def outputs_upsert(con: Client, rid: str, **paths: str) -> None:
    """Insert or update output file paths for a request."""
    res = con.table("outputs").select("req_id").eq("req_id", rid).limit(1).execute()
    if not res.data:
        con.table("outputs").insert({
            "req_id": rid, "created_at": now_str(), "updated_at": now_str(),
        }).execute()
    update_fields = {k: v for k, v in paths.items() if v is not None}
    if update_fields:
        update_fields["updated_at"] = now_str()
        con.table("outputs").update(update_fields).eq("req_id", rid).execute()


def outputs_get(con: Client, rid: str) -> Optional[Dict[str, Any]]:
    """Get the outputs record for a request."""
    res = con.table("outputs").select("*").eq("req_id", rid).limit(1).execute()
    return res.data[0] if res.data else None


def zip_build(con: Client, rid: str, out_zip: Path, include_files: List[Path]) -> Path:
    """Build a ZIP archive from the given files."""
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as z:
        for f in include_files:
            if f and f.exists():
                z.write(str(f), arcname=f.name)
    return out_zip


def generate_all_outputs(con: Client, rid: str) -> Dict[str, str]:
    """Generate all output files (PDFs, QR, ZIP) for a request."""
    req = req_get(con, rid)
    if not req:
        raise ValueError("요청을 찾을 수 없습니다.")
    out = path_output()
    approvals = approvals_for_req(con, rid)
    exec_row = execution_get(con, rid)
    photos = photos_for_req(con, rid)
    sic_default = settings_get(con, "sic_training_url_default", "https://example.com/visitor-training")
    sic_url = (req.get("sic_training_url") or "").strip() or sic_default

    # day_seq 직접 계산 — 반입예정일(date) 기준 당일 순번
    planned_date = (req.get('date') or req.get('created_at') or '')[:10]
    pid = req.get('project_id', '')
    same_day_res = (con.table("requests")
                    .select("id,created_at")
                    .eq("project_id", pid).eq("date", planned_date)
                    .order("created_at").order("id").execute())
    same_day_rows = same_day_res.data or []
    day_seq = 1
    for i, r in enumerate(same_day_rows, start=1):
        if r["id"] == rid:
            day_seq = i
            break
    req['day_seq'] = day_seq
    disp = req_display_id(req)

    qr_path = out["qr"] / f"{disp}_sic_qr.png"
    qr_saved = qr_generate_png(sic_url, qr_path) if QR_AVAILABLE else None
    qr_storage = _upload_artifact(con, "qr", rid, qr_saved)
    if qr_storage:
        outputs_upsert(con, rid, qr_png_path=qr_storage)

    plan_pdf = out["plan"] / f"{disp}_plan.pdf"
    pdf_plan(con, req, approvals, plan_pdf, photos=photos)

    permit_pdf = out["permit"] / f"{disp}_permit.pdf"
    pdf_permit(con, req, sic_url, qr_saved, permit_pdf)

    check_pdf: Optional[Path] = None
    check_json: Dict[str, Any] = {}
    if exec_row and exec_row.get("check_json"):
        try:
            check_json = json.loads(exec_row["check_json"])
        except Exception:
            check_json = {}
        check_pdf = out["check"] / f"{disp}_checkcard.pdf"
        pdf_check_card(con, req, check_json, check_pdf)

    exec_pdf = out["exec"] / f"{disp}_exec.pdf"
    pdf_exec_summary(con, req, photos, exec_pdf)

    bundle_pdf = out["bundle"] / f"{disp}_bundle.pdf"
    c = canvas.Canvas(str(bundle_pdf), pagesize=A4)
    pdf_simple_header(c, "산출물 번들 안내", f"요청ID: {rid} · 생성: {now_str()} · {APP_VERSION}")
    c.setFont("Helvetica", 11)
    c.drawString(20 * mm, 260 * mm, "아래 파일들이 함께 생성되었습니다.")
    c.setFont("Helvetica", 10)
    y = 248 * mm
    for f in [plan_pdf, permit_pdf, check_pdf, exec_pdf, qr_saved]:
        if f and Path(f).exists():
            c.drawString(22 * mm, y, f"- {Path(f).name}")
            y -= 7 * mm
    c.drawString(20 * mm, 220 * mm, f"저장 위치: {str(path_output_root())}")
    c.showPage()
    c.save()

    zip_path = out["zip"] / f"{disp}_outputs.zip"
    include: List[Path] = [plan_pdf, permit_pdf, exec_pdf, bundle_pdf]
    if check_pdf:
        include.append(check_pdf)
    if qr_saved:
        include.append(qr_saved)
    for p in photos:
        fp = Path(p.get("file_path") or "")
        if fp.exists():
            include.append(fp)
    zip_build(con, rid, zip_path, include)

    plan_storage   = _upload_artifact(con, "plan",   rid, plan_pdf)
    permit_storage = _upload_artifact(con, "permit", rid, permit_pdf)
    check_storage  = _upload_artifact(con, "check",  rid, check_pdf) if check_pdf else ""
    exec_storage   = _upload_artifact(con, "exec",   rid, exec_pdf)
    bundle_storage = _upload_artifact(con, "bundle", rid, bundle_pdf)
    zip_storage    = _upload_artifact(con, "zip",    rid, zip_path)

    outputs_upsert(
        con, rid,
        plan_pdf_path=plan_storage   or str(plan_pdf),
        permit_pdf_path=permit_storage or str(permit_pdf),
        check_pdf_path=check_storage  or (str(check_pdf) if check_pdf else ""),
        exec_pdf_path=exec_storage    or str(exec_pdf),
        bundle_pdf_path=bundle_storage or str(bundle_pdf),
        zip_path=zip_storage or str(zip_path),
    )
    return {
        "plan_pdf": plan_storage   or str(plan_pdf),
        "permit_pdf": permit_storage or str(permit_pdf),
        "check_pdf": check_storage  or (str(check_pdf) if check_pdf else ""),
        "exec_pdf": exec_storage    or str(exec_pdf),
        "bundle_pdf": bundle_storage or str(bundle_pdf),
        "zip": zip_storage or str(zip_path),
        "qr": qr_storage or (str(qr_saved) if qr_saved else ""),
        "root": str(path_output_root()),
    }
