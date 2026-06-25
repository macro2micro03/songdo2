"""접속 로그 기록 헬퍼."""
from shared.helpers import now_str, new_id


def log_access(con, project_id: str, username: str, user_name: str,
               user_role: str, action: str, page: str = "") -> None:
    try:
        con.table("access_logs").insert({
            "id":         new_id(),
            "project_id": project_id,
            "username":   username,
            "user_name":  user_name,
            "user_role":  user_role,
            "action":     action,
            "page":       page,
            "created_at": now_str(),
        }).execute()
    except Exception:
        pass
