"""Execution CRUD operations."""

from shared.timing import measure
import json
import uuid
from pathlib import Path
from typing import Dict, Any, List, Optional

from supabase import Client

from shared.helpers import now_str, file_sha1
from shared.storage import delete_photo_paths, upload_photo
from config import EXEC_REQUIRED_PHOTOS


def photo_exists_same(con: Client, rid: str, slot_key: str, file_hash: str) -> bool:
    """Check if a photo with the same hash already exists for the given slot."""
    res = (con.table("photos").select("id")
           .eq("req_id", rid).eq("slot_key", slot_key).eq("file_hash", file_hash)
           .limit(1).execute())
    return bool(res.data)


def photo_add(
    con: Client,
    rid: str,
    slot_key: str,
    label: str,
    file_bytes: bytes,
    suffix: str = ".jpg",
) -> str:
    """Upload a photo to Supabase Storage and record it in the photos table.

    Returns the public URL on success, or an empty string if the same image
    (same hash) is already attached to the same slot.
    """
    fhash = file_sha1(file_bytes)
    if photo_exists_same(con, rid, slot_key, fhash):
        return ""
    storage_path, url = upload_photo(con, rid, slot_key, file_bytes, suffix)
    con.table("photos").insert({
        "id": uuid.uuid4().hex,
        "req_id": rid,
        "slot_key": slot_key,
        "label": label,
        "file_path": storage_path,
        "storage_url": url,
        "file_hash": fhash,
        "created_at": now_str(),
    }).execute()
    return url


def photo_delete_slot(con: Client, rid: str, slot_key: str) -> None:
    """Delete photo record(s) for a slot and remove the corresponding storage objects."""
    res = (con.table("photos").select("file_path,storage_url")
           .eq("req_id", rid).eq("slot_key", slot_key).execute())
    storage_paths: List[str] = []
    for row in res.data or []:
        fp = row.get("file_path") or ""
        if fp and not fp.startswith(("http://", "https://", "C:", "/")):
            storage_paths.append(fp)
    delete_photo_paths(con, storage_paths)
    # Best-effort: also unlink legacy local files (pre-Storage records)
    for row in res.data or []:
        fp = row.get("file_path") or ""
        if fp.startswith(("C:", "/")):
            try:
                Path(fp).unlink(missing_ok=True)
            except Exception:
                pass
    con.table("photos").delete().eq("req_id", rid).eq("slot_key", slot_key).execute()


@measure("crud.photos_for_req")


def photos_for_req(con: Client, rid: str) -> List[Dict[str, Any]]:
    """Get all photos for a given request."""
    res = (con.table("photos").select("*").eq("req_id", rid)
           .order("created_at").execute())
    return res.data or []


def required_photos_ok(con: Client, rid: str) -> bool:
    """Check if all required photos have been uploaded for a request."""
    keys = {p["slot_key"] for p in photos_for_req(con, rid)}
    return all(k in keys for k, _ in EXEC_REQUIRED_PHOTOS)


def execution_upsert(
    con: Client,
    rid: str,
    executed_by: str,
    executed_role: str,
    check_json: Dict[str, Any],
    notes: str,
) -> None:
    """Insert or update an execution record."""
    ok = 1 if required_photos_ok(con, rid) else 0
    con.table("executions").upsert({
        "req_id": rid,
        "executed_by": executed_by,
        "executed_role": executed_role,
        "executed_at": now_str(),
        "check_json": json.dumps(check_json, ensure_ascii=False),
        "required_photo_ok": ok,
        "notes": notes,
    }, on_conflict="req_id").execute()


@measure("crud.execution_get")


def execution_get(con: Client, rid: str) -> Optional[Dict[str, Any]]:
    """Get the execution record for a request."""
    res = con.table("executions").select("*").eq("req_id", rid).limit(1).execute()
    return res.data[0] if res.data else None


def final_approved_signs(con: Client, rid: str) -> List[Dict[str, Any]]:
    """Get all approved signatures for a request."""
    res = (con.table("approvals").select("*")
           .eq("req_id", rid).eq("status", "APPROVED")
           .order("step_no").execute())
    return res.data or []
