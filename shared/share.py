"""Share text generation for KakaoTalk / messenger sharing."""

from pathlib import Path
from typing import Dict, Any, Optional

from config import KIND_IN


def make_share_text(req: Dict[str, Any], outs: Optional[Dict[str, Any]]) -> str:
    """Build a human-readable share string for a request + its outputs."""
    kind_txt = "반입" if req["kind"] == KIND_IN else "반출"

    # gate 파싱 (Zone|장소)
    gate_raw = req.get("gate", "")
    if "|" in gate_raw:
        parts = gate_raw.split("|", 1)
        gate_disp = f"{parts[0].strip()} / {parts[1].strip()}"
    else:
        gate_disp = gate_raw

    STATUS_KR = {
        "PENDING_APPROVAL": "승인 대기",
        "APPROVED":         "승인됨",
        "REJECTED":         "반려됨",
        "EXECUTING":        "실행중",
        "DONE":             "완료",
    }
    status_disp = STATUS_KR.get(req.get("status", ""), req.get("status", ""))

    lines = []
    lines.append(f"[자재 {kind_txt}] {req.get('date','')}  {req.get('time_from','')}~{req.get('time_to','')}")
    lines.append(f"· 장소: {gate_disp}")
    lines.append(f"· 업체명: {req.get('company_name','')}")
    lines.append(f"· 자재종류: {req.get('item_name','')}")

    loading = req.get("loading_method", "")
    if loading:
        lines.append(f"· 상·하차 방식: {loading}")

    vton  = req.get("vehicle_ton", "")
    vcnt  = req.get("vehicle_count", "")
    if vton or vcnt:
        lines.append(f"· 차량: {vton}  {vcnt}대")

    sup   = req.get("worker_supervisor", "")
    guide = req.get("worker_guide", "")
    mgr   = req.get("worker_manager", "")
    if sup or guide or mgr:
        worker_parts = []
        if sup:   worker_parts.append(f"작업지휘자 {sup}")
        if guide: worker_parts.append(f"유도원 {guide}")
        if mgr:   worker_parts.append(f"담당자 {mgr}")
        lines.append(f"· {' / '.join(worker_parts)}")

    notes = req.get("notes", "")
    if notes:
        lines.append(f"· 비고: {notes}")

    lines.append(f"· 상태: {status_disp}")

    if outs:
        doc_title = "자재반입계획서" if req["kind"] == KIND_IN else "반출사진"
        lines.append("")
        lines.append("— 산출물 —")
        if outs.get("plan_pdf_path"):
            lines.append(f"  · {doc_title}: {Path(outs.get('plan_pdf_path')).name}")

    return "\n".join(lines)
