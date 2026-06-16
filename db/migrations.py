"""Database migration logic – table creation and schema evolution."""
import json
import sqlite3
from typing import List

from shared.helpers import now_str


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def table_cols(cur: sqlite3.Cursor, table: str) -> List[str]:
    """Return column names for *table*."""
    cur.execute(f"PRAGMA table_info({table})")
    return [r[1] for r in cur.fetchall()]


def add_col_if_missing(cur: sqlite3.Cursor, table: str, coldef: str) -> None:
    """Add a column described by *coldef* (e.g. ``'file_hash TEXT'``) if absent."""
    col = coldef.split()[0]
    if col not in table_cols(cur, table):
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {coldef}")


# ---------------------------------------------------------------------------
# Main migration entry-point
# ---------------------------------------------------------------------------

def db_init_and_migrate(con: sqlite3.Connection) -> None:
    """Create every table (if missing) and apply incremental column additions."""
    cur = con.cursor()

    # ── core tables ────────────────────────────────────────────────────────
    cur.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS requests (
        id TEXT PRIMARY KEY,
        project_id TEXT DEFAULT '',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        status TEXT NOT NULL,
        kind TEXT NOT NULL,
        company_name TEXT,
        item_name TEXT,
        item_type TEXT,
        work_type TEXT,
        date TEXT,
        time_from TEXT,
        time_to TEXT,
        gate TEXT,
        vehicle_type TEXT,
        vehicle_ton TEXT,
        vehicle_count INTEGER,
        driver_name TEXT,
        driver_phone TEXT,
        notes TEXT,
        requester_name TEXT,
        requester_role TEXT,
        risk_level TEXT,
        sic_training_url TEXT
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS approvals (
        id TEXT PRIMARY KEY,
        req_id TEXT NOT NULL,
        step_no INTEGER NOT NULL,
        role_required TEXT NOT NULL,
        status TEXT NOT NULL,
        signer_name TEXT,
        signer_role TEXT,
        sign_png_path TEXT,
        stamp_png_path TEXT,
        signed_at TEXT,
        reject_reason TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY(req_id) REFERENCES requests(id)
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS executions (
        req_id TEXT PRIMARY KEY,
        executed_by TEXT,
        executed_role TEXT,
        executed_at TEXT,
        check_json TEXT,
        required_photo_ok INTEGER DEFAULT 0,
        notes TEXT,
        FOREIGN KEY(req_id) REFERENCES requests(id)
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS photos (
        id TEXT PRIMARY KEY,
        req_id TEXT NOT NULL,
        slot_key TEXT,
        label TEXT,
        file_path TEXT NOT NULL,
        file_hash TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY(req_id) REFERENCES requests(id)
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS outputs (
        req_id TEXT PRIMARY KEY,
        plan_pdf_path TEXT,
        permit_pdf_path TEXT,
        check_pdf_path TEXT,
        exec_pdf_path TEXT,
        bundle_pdf_path TEXT,
        zip_path TEXT,
        qr_png_path TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY(req_id) REFERENCES requests(id)
    );
    """)

    # ── multi-project tables ───────────────────────────────────────────────
    cur.execute("""
    CREATE TABLE IF NOT EXISTS projects (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        description TEXT DEFAULT '',
        site_pin TEXT NOT NULL,
        admin_pin TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS project_modules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id TEXT NOT NULL,
        module_key TEXT NOT NULL,
        module_name TEXT NOT NULL,
        module_desc TEXT DEFAULT '',
        enabled INTEGER DEFAULT 1,
        sort_order INTEGER DEFAULT 0,
        FOREIGN KEY(project_id) REFERENCES projects(id),
        UNIQUE(project_id, module_key)
    );
    """)

    # ── users table (account-based auth) ──────────────────────────────────
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        username TEXT NOT NULL,
        password_hash TEXT NOT NULL,
        salt TEXT NOT NULL,
        name TEXT NOT NULL,
        role TEXT NOT NULL,
        is_admin INTEGER DEFAULT 0,
        created_at TEXT NOT NULL,
        UNIQUE(project_id, username),
        FOREIGN KEY(project_id) REFERENCES projects(id)
    );
    """)

    # ── schedules table ────────────────────────────────────────────────────
    cur.execute("""
    CREATE TABLE IF NOT EXISTS schedules (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        req_id TEXT,
        title TEXT NOT NULL,
        schedule_date TEXT NOT NULL,
        time_from TEXT NOT NULL,
        time_to TEXT NOT NULL,
        kind TEXT DEFAULT 'IN',
        gate TEXT DEFAULT '',
        company_name TEXT DEFAULT '',
        vehicle_info TEXT DEFAULT '',
        status TEXT DEFAULT 'PENDING',
        color TEXT DEFAULT '#fbbf24',
        created_by TEXT DEFAULT '',
        created_at TEXT NOT NULL,
        FOREIGN KEY(project_id) REFERENCES projects(id)
    );
    """)
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_schedules_date "
        "ON schedules(project_id, schedule_date);"
    )

    cur.execute("""
    CREATE TABLE IF NOT EXISTS terminal_releases (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        terminal TEXT NOT NULL,
        release_date TEXT NOT NULL,
        created_at TEXT NOT NULL,
        created_by TEXT DEFAULT '',
        UNIQUE(project_id, terminal, release_date)
    );
    """)

    con.commit()

    # ── incremental column migrations ──────────────────────────────────────
    add_col_if_missing(cur, "photos", "file_hash TEXT")
    add_col_if_missing(cur, "requests", "project_id TEXT DEFAULT ''")
    add_col_if_missing(cur, "users", "company_name TEXT DEFAULT ''")
    add_col_if_missing(cur, "users", "updated_at TEXT DEFAULT ''")
    add_col_if_missing(cur, "requests", "worker_supervisor TEXT DEFAULT ''")
    add_col_if_missing(cur, "requests", "worker_guide TEXT DEFAULT ''")
    add_col_if_missing(cur, "requests", "worker_manager TEXT DEFAULT ''")
    add_col_if_missing(cur, "requests", "loading_method TEXT DEFAULT ''")
    # 예약존(booking_zone) 컬럼 추가
    add_col_if_missing(cur, "requests",  "booking_zone TEXT DEFAULT 'A'")
    add_col_if_missing(cur, "schedules", "booking_zone TEXT DEFAULT 'A'")
    con.commit()
    # 기존 NULL 값을 'A'로 초기화
    cur.execute("UPDATE requests  SET booking_zone='A' WHERE booking_zone IS NULL OR booking_zone=''")
    cur.execute("UPDATE schedules SET booking_zone='A' WHERE booking_zone IS NULL OR booking_zone=''")
    con.commit()

    # ── settings 기본값 ────────────────────────────────────────────────────
    set_default(con, "booking_zones_json", '["A"]')
    set_default(con, "booking_zones_disabled_json", "[]")

    # ── dashboard 모듈 기존 프로젝트에 추가 ──────────────────────────────
    cur.execute("SELECT id FROM projects")
    for proj_row in cur.fetchall():
        pid = proj_row[0]
        cur.execute(
            "SELECT id FROM project_modules WHERE project_id=? AND module_key='dashboard'",
            (pid,),
        )
        if not cur.fetchone():
            cur.execute(
                """INSERT INTO project_modules
                   (project_id, module_key, module_name, module_desc, enabled, sort_order)
                   VALUES(?,?,?,?,?,?)""",
                (pid, "dashboard", "📊 대시보드", "날짜별 반출입 현황 요약", 1, -1),
            )
    # sort_order 재정렬: dashboard=-1 → 0, 기존 모듈 +1
    sort_map_v2 = {
        "schedule": 0, "approval": 1, "execution": 2,
        "outputs": 3, "ledger": 4, "dashboard": 5,
    }
    for key, order in sort_map_v2.items():
        cur.execute(
            "UPDATE project_modules SET sort_order=? WHERE module_key=?",
            (order, key),
        )
    con.commit()

    # ── module merge migration: request → schedule 통합 ──────────────────
    # request 모듈 삭제 (schedule 탭으로 통합, 레거시 항목 완전 제거)
    cur.execute("DELETE FROM project_modules WHERE module_key='request'")
    # schedule 모듈 이름/설명 업데이트
    cur.execute(
        "UPDATE project_modules SET module_name=?, module_desc=? WHERE module_key='schedule'",
        ("📅 신청", "일정 캘린더 + 신규 요청 등록 통합"),
    )
    # outputs 모듈 이름 업데이트
    cur.execute(
        "UPDATE project_modules SET module_name=? WHERE module_key='outputs'",
        ("📄 계획서",),
    )
    # execution 모듈 이름 업데이트
    cur.execute(
        "UPDATE project_modules SET module_name=? WHERE module_key='execution'",
        ("📸 사진등록",),
    )
    # sort_order 재정렬: schedule=0, approval=1, execution=2, outputs=3, ledger=4
    sort_map = {
        "schedule": 0, "approval": 1, "execution": 2, "outputs": 3, "ledger": 4,
    }
    for key, order in sort_map.items():
        cur.execute(
            "UPDATE project_modules SET sort_order=? WHERE module_key=?",
            (order, key),
        )
    # enabled_admin / enabled_user 컬럼 추가 (없을 때만)
    existing = {r[1] for r in cur.execute("PRAGMA table_info(project_modules)").fetchall()}
    if "enabled_admin" not in existing:
        cur.execute("ALTER TABLE project_modules ADD COLUMN enabled_admin INTEGER DEFAULT 1")
        cur.execute("UPDATE project_modules SET enabled_admin = enabled")
    if "enabled_user" not in existing:
        cur.execute("ALTER TABLE project_modules ADD COLUMN enabled_user INTEGER DEFAULT 1")
        cur.execute("UPDATE project_modules SET enabled_user = enabled")

    con.commit()


# ---------------------------------------------------------------------------
# Settings defaults
# ---------------------------------------------------------------------------

def set_default(con: sqlite3.Connection, key: str, val: str) -> None:
    """Insert a settings row only if *key* does not already exist."""
    cur = con.cursor()
    cur.execute("SELECT value FROM settings WHERE key=?", (key,))
    if not cur.fetchone():
        cur.execute(
            "INSERT INTO settings(key, value, updated_at) VALUES(?, ?, ?)",
            (key, val, now_str()),
        )
        con.commit()
