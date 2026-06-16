"""Supabase Storage helpers — bucket uploads, signed URLs, local cache."""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Iterable, Optional, Tuple

from supabase import Client

from db.connection import get_base_dir, outputs_bucket, photos_bucket


# ── Upload ────────────────────────────────────────────────────────────────

def upload_bytes(sb: Client, bucket: str, path: str, data: bytes,
                 content_type: str = "application/octet-stream",
                 upsert: bool = True) -> str:
    """Upload bytes to ``bucket/path``. Returns the storage object path."""
    sb.storage.from_(bucket).upload(
        path=path,
        file=data,
        file_options={
            "content-type": content_type,
            "x-upsert": "true" if upsert else "false",
        },
    )
    return path


def public_url(sb: Client, bucket: str, path: str) -> str:
    """Public URL (works only when bucket is public)."""
    return sb.storage.from_(bucket).get_public_url(path)


def signed_url(sb: Client, bucket: str, path: str, expires: int = 3600) -> str:
    res = sb.storage.from_(bucket).create_signed_url(path, expires)
    return res.get("signedURL") or res.get("signed_url") or ""


# ── Photo (public bucket) ─────────────────────────────────────────────────

def upload_photo(sb: Client, rid: str, slot_key: str, data: bytes,
                 suffix: str = ".jpg") -> Tuple[str, str]:
    """Upload to the photos bucket. Returns (storage_path, public_url)."""
    bucket = photos_bucket()
    path = f"{rid}/{slot_key}_{uuid.uuid4().hex[:8]}{suffix}"
    upload_bytes(sb, bucket, path, data, content_type=_guess_ct(suffix))
    return path, public_url(sb, bucket, path)


def delete_photo_paths(sb: Client, paths: Iterable[str]) -> None:
    """Delete object(s) from the photos bucket. Silently ignores missing objects."""
    paths = [p for p in (paths or []) if p]
    if not paths:
        return
    try:
        sb.storage.from_(photos_bucket()).remove(paths)
    except Exception:
        pass


# ── Output (private bucket) ───────────────────────────────────────────────

def upload_output(sb: Client, kind: str, rid: str, suffix: str,
                  data: bytes, unique: bool = False) -> str:
    """Upload a generated artifact (pdf/zip/png). Returns the storage path.

    ``unique=True`` adds a random tag — use it for files where each upload should
    produce a distinct object (signatures, stamps). Default behaviour overwrites
    the same key, which is what we want for regenerated PDFs/QRs.
    """
    bucket = outputs_bucket()
    tag = f"_{uuid.uuid4().hex[:8]}" if unique else ""
    path = f"{kind}/{rid}{tag}{suffix}"
    upload_bytes(sb, bucket, path, data, content_type=_guess_ct(suffix))
    return path


def output_url(sb: Client, path: str, expires: int = 3600) -> str:
    """Signed URL for a private outputs object."""
    if not path:
        return ""
    return signed_url(sb, outputs_bucket(), path, expires)


# ── Local cache (downloads on demand) ─────────────────────────────────────

def cache_to_local(sb: Client, bucket: str, path: str) -> Optional[Path]:
    """Download object to a local cache dir under BASE_DIR/tmp_cache. Returns the cached path
    (re-used if already cached). Returns None on failure."""
    if not path:
        return None
    cache_root = get_base_dir() / "tmp_cache" / bucket
    cache_root.mkdir(parents=True, exist_ok=True)
    cached = cache_root / path.replace("/", "__")
    if cached.exists() and cached.stat().st_size > 0:
        return cached
    try:
        data = sb.storage.from_(bucket).download(path)
    except Exception:
        return None
    if not data:
        return None
    cached.write_bytes(data)
    return cached


# ── Helpers ───────────────────────────────────────────────────────────────

_CT_MAP = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".pdf": "application/pdf", ".zip": "application/zip",
}


def _guess_ct(suffix: str) -> str:
    return _CT_MAP.get(suffix.lower(), "application/octet-stream")
