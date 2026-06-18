"""Authentication and session management — Supabase Auth (신규) + PBKDF2 (legacy fallback).

신규 가입: Supabase Auth `sign_up`(email/password) → profiles 행에 supabase_uid + email 저장
기존 PBKDF2 계정: profiles.password_hash/salt 로컬 검증 (마이그레이션 안 함)
비밀번호 재설정: Supabase Auth `reset_password_for_email` → OTP 코드 메일 발송 →
                `verify_otp(type='recovery')` → `update_user(password=...)`
"""
import hashlib
import os
from typing import Dict, Optional, Tuple

import streamlit as st
from supabase import Client

from shared.helpers import new_id, now_str


# ── 비밀번호 해싱 (legacy PBKDF2-SHA256) ──────────────────────────────────

def _new_salt() -> str:
    return os.urandom(16).hex()


def _hash_pw(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000
    ).hex()


def _make_email(project_id: str, username: str) -> str:
    """레거시: 합성 이메일 (수신 불가). 신규 계정은 실 이메일을 사용."""
    return f"{username.strip()}@{project_id[:8]}.gate"


def _norm_email(email: str) -> str:
    return (email or "").strip().lower()


# ── 계정 CRUD ─────────────────────────────────────────────────────────

def user_create(sb: Client, project_id: str, username: str, password: str,
                name: str, role: str, is_admin: bool = False,
                company_name: str = "", email: str = "") -> Tuple[bool, str]:
    """신규 계정 생성 — PBKDF2 자체 계정 (profiles 에 password_hash/salt 저장).

    Supabase Auth `sign_up` 을 호출하지 않으므로 가입 시 확인 메일이 발송되지
    않는다(내장 이메일 rate limit 회피). 이메일은 저장만 하며, 향후 커스텀
    SMTP 연결 시 Supabase Auth 기반 이메일 재설정으로 전환할 수 있다.
    로그인은 user_authenticate 의 PBKDF2 경로로 처리된다.
    """
    if len(password) < 6:
        return False, "비밀번호는 6자 이상이어야 합니다."
    email = _norm_email(email)
    if not email or "@" not in email or "." not in email.split("@")[-1]:
        return False, "올바른 이메일 주소를 입력하세요."

    # 1) 같은 프로젝트 내 아이디 중복 체크
    dup = (sb.table("profiles").select("id")
           .eq("project_id", project_id)
           .eq("username", username.strip())
           .limit(1).execute())
    if dup.data:
        return False, "이미 사용 중인 아이디입니다."

    # 1-1) profiles 의 email 중복 체크 (다른 username 으로 같은 이메일 등록 방지)
    dup_em = (sb.table("profiles").select("id,username")
              .eq("email", email).limit(1).execute())
    if dup_em.data:
        return False, "이미 가입된 이메일입니다."

    # 2) PBKDF2 자격증명 생성 (Supabase Auth 미사용 → 확인 메일 미발송으로 rate limit 회피)
    salt = _new_salt()
    pw_hash = _hash_pw(password, salt)

    # 3) profiles 행 INSERT (PBKDF2 자격증명 저장, supabase_uid 는 NULL — 이메일은 보관)
    try:
        sb.table("profiles").insert({
            "id":            new_id(),
            "project_id":    project_id,
            "username":      username.strip(),
            "name":          name.strip(),
            "role":          role,
            "is_admin":      int(is_admin),
            "supabase_uid":  None,
            "email":         email,
            "password_hash": pw_hash,
            "salt":          salt,
            "company_name":  company_name.strip(),
            "created_at":    now_str(),
            "updated_at":    now_str(),
        }).execute()
    except Exception as e:
        return False, f"가입 실패: {e}"

    return True, "계정이 생성되었습니다. 바로 로그인하세요."


def user_authenticate(sb: Client, project_id: str, username: str,
                      password: str) -> Tuple[bool, Optional[Dict], str]:
    """자격증명 검증. (success, user_dict|None, error_code).

    error_code: "" | "NOT_FOUND" | "BAD_PASSWORD" | "EMAIL_NOT_CONFIRMED" | "OTHER"
    """
    res = (sb.table("profiles").select("*")
           .eq("project_id", project_id)
           .eq("username", username.strip())
           .limit(1).execute())
    if not res.data:
        return False, None, "NOT_FOUND"
    user = res.data[0]

    # 경로 A: 로컬 PBKDF2 (legacy 계정)
    if user.get("password_hash") and user.get("salt"):
        if _hash_pw(password, user["salt"]) != user["password_hash"]:
            return False, None, "BAD_PASSWORD"
        return True, user, ""

    # 경로 B: Supabase Auth — 실 이메일 (신규 계정)
    if user.get("supabase_uid") and user.get("email"):
        try:
            res_auth = sb.auth.sign_in_with_password({
                "email":    user["email"],
                "password": password,
            })
            if not getattr(res_auth, "user", None):
                return False, None, "BAD_PASSWORD"
            st.session_state["SUPABASE_SESSION"] = res_auth.session
            return True, user, ""
        except Exception as e:
            msg = str(e).lower()
            if "not confirmed" in msg or "email_not_confirmed" in msg or "confirm" in msg:
                return False, None, "EMAIL_NOT_CONFIRMED"
            return False, None, "BAD_PASSWORD"

    # 경로 C: 레거시 Supabase Auth (합성 이메일, supabase_uid 만 보유)
    if user.get("supabase_uid"):
        try:
            res_auth = sb.auth.sign_in_with_password({
                "email":    _make_email(project_id, username),
                "password": password,
            })
            if not getattr(res_auth, "user", None):
                return False, None, "BAD_PASSWORD"
            st.session_state["SUPABASE_SESSION"] = res_auth.session
            return True, user, ""
        except Exception:
            return False, None, "BAD_PASSWORD"

    return False, None, "OTHER"


def project_has_users(sb: Client, project_id: str) -> bool:
    res = sb.table("profiles").select("id").eq("project_id", project_id).limit(1).execute()
    return bool(res.data)


def user_list(sb: Client, project_id: str):
    res = (sb.table("profiles")
           .select("id,username,name,role,is_admin,is_sysadmin,company_name,email,created_at")
           .eq("project_id", project_id)
           .order("created_at", desc=True)
           .execute())
    return res.data or []


def user_delete(sb: Client, user_id: str) -> None:
    sb.table("profiles").delete().eq("id", user_id).execute()


def set_user_admin(sb: Client, user_id: str, make_admin: bool) -> Tuple[bool, str]:
    """관리자(is_admin) 권한 부여/해제.

    - 권한 검증(부여=관리자 이상, 해제=시스템관리자)은 호출 측 UI 에서 수행
    - 시스템관리자(is_sysadmin)는 이 함수로 변경하지 않음 (DB/개발자 전용)
    """
    sb.table("profiles").update({
        "is_admin":   int(bool(make_admin)),
        "updated_at": now_str(),
    }).eq("id", user_id).execute()
    return True, ("관리자 권한을 부여했습니다." if make_admin
                  else "관리자 권한을 해제했습니다.")


def admin_reset_user_password(sb: Client, user_id: str,
                              new_password: str) -> Tuple[bool, str]:
    """관리자용 — 다른 사용자의 비밀번호를 임시 비밀번호로 재설정 (PBKDF2 경로).

    NOTE: 신규 Supabase Auth 계정에는 이 헬퍼가 적용되지 않습니다.
    Supabase Auth 계정의 관리자 reset 은 Service Role Key 가 필요해 클라이언트에서 직접 수행 불가.
    Supabase Auth 계정 사용자는 셀프 reset(메일 OTP) 흐름을 이용해야 합니다.
    """
    if not new_password or len(new_password) < 6:
        return False, "비밀번호는 6자 이상이어야 합니다."
    salt    = _new_salt()
    pw_hash = _hash_pw(new_password, salt)
    sb.table("profiles").update({
        "password_hash": pw_hash,
        "salt":          salt,
        "supabase_uid":  None,
        "updated_at":    now_str(),
    }).eq("id", user_id).execute()
    return True, "비밀번호가 재설정되었습니다."


# ── 비밀번호 재설정 (셀프서비스 — Supabase Auth 메일 OTP) ────────────

def request_password_reset(sb: Client, project_id: str,
                           username: str) -> Tuple[bool, str, str]:
    """username 으로 profiles.email 을 조회 → reset 메일 발송.

    Returns (success, message, email_for_next_step).
    레거시 PBKDF2 계정처럼 셀프 reset 이 불가한 경우 success=False.
    """
    res = (sb.table("profiles").select("email,supabase_uid")
           .eq("project_id", project_id)
           .eq("username", username.strip())
           .limit(1).execute())
    if not res.data:
        return False, "해당 아이디를 찾을 수 없습니다.", ""

    row   = res.data[0]
    email = row.get("email") or ""
    if not email or not row.get("supabase_uid"):
        return False, "이 계정은 셀프 재설정을 지원하지 않습니다. 관리자에게 문의하세요.", ""

    try:
        sb.auth.reset_password_for_email(email)
    except Exception as e:
        return False, f"재설정 메일 발송 실패: {e}", ""

    return True, "재설정 메일을 발송했습니다. 메일의 8자리 코드를 입력하세요.", email


def verify_reset_and_update(sb: Client, email: str, token: str,
                            new_password: str) -> Tuple[bool, str]:
    """OTP 코드를 검증한 뒤 새 비밀번호로 변경."""
    if not new_password or len(new_password) < 6:
        return False, "비밀번호는 6자 이상이어야 합니다."
    if not token.strip():
        return False, "인증 코드를 입력하세요."

    email = _norm_email(email)
    try:
        res = sb.auth.verify_otp({
            "email": email,
            "token": token.strip(),
            "type":  "recovery",
        })
        if not getattr(res, "session", None):
            return False, "코드가 올바르지 않거나 만료되었습니다."
        sb.auth.update_user({"password": new_password})
    except Exception:
        return False, "코드가 올바르지 않거나 만료되었습니다."
    finally:
        try:
            sb.auth.sign_out()
        except Exception:
            pass

    return True, "비밀번호가 변경되었습니다. 새 비밀번호로 로그인하세요."


# ── 세션 헬퍼 ─────────────────────────────────────────────────────────

def auth_reset() -> None:
    st.session_state["AUTH_OK"]     = False
    st.session_state["IS_ADMIN"]    = False
    st.session_state["IS_SYSADMIN"] = False
    st.session_state["USER_NAME"]  = ""
    st.session_state["USER_ROLE"]  = "협력사"
    st.session_state["ACTIVE_PAGE"] = "홈"
    st.session_state.pop("SUPABASE_SESSION", None)
    # localStorage에서 로그인 정보 삭제
    clear_auth_from_storage()


def auth_login(sb: Client, username: str, password: str) -> Tuple[bool, str]:
    project_id = st.session_state.get("PROJECT_ID", "")
    ok, user, err = user_authenticate(sb, project_id, username, password)
    if not ok or not user:
        if err == "EMAIL_NOT_CONFIRMED":
            return False, "이메일 확인이 필요합니다. 가입 시 받은 메일의 인증 링크를 클릭한 뒤 다시 시도하세요."
        return False, "아이디 또는 비밀번호가 올바르지 않습니다."
    is_sysadmin = bool(user.get("is_sysadmin"))
    st.session_state["AUTH_OK"]      = True
    # 시스템관리자는 관리자 권한 상위호환 → 관리자 페이지/기능 모두 접근
    st.session_state["IS_ADMIN"]     = bool(user.get("is_admin")) or is_sysadmin
    st.session_state["IS_SYSADMIN"]  = is_sysadmin
    st.session_state["USER_NAME"]    = user.get("name", "")
    st.session_state["USER_ROLE"]    = user.get("role", "협력사")
    st.session_state["USER_COMPANY"] = user.get("company_name", "") or ""
    st.session_state["USER_ID"]      = user.get("username", "")
    return True, "로그인 완료"


def session_has_project() -> bool:
    return bool(st.session_state.get("PROJECT_ID"))


def session_is_authed() -> bool:
    return st.session_state.get("AUTH_OK", False)


def current_project_id() -> str:
    return st.session_state.get("PROJECT_ID", "")


# ── localStorage 지속성 ────────────────────────────────────────
def persist_auth_to_storage() -> None:
    """현재 로그인 정보를 localStorage에 저장하는 JavaScript 실행"""
    import json, base64
    auth_data = {
        "username": st.session_state.get("USER_ID", ""),
        "name": st.session_state.get("USER_NAME", ""),
        "role": st.session_state.get("USER_ROLE", ""),
        "is_admin": st.session_state.get("IS_ADMIN", False),
        "project_id": st.session_state.get("PROJECT_ID", ""),
    }
    auth_json = json.dumps(auth_data)
    auth_b64 = base64.b64encode(auth_json.encode()).decode()

    st.markdown(f"""
    <script>
    localStorage.setItem('_app_auth', '{auth_b64}');
    </script>
    """, unsafe_allow_html=True)


def restore_auth_from_storage(sb: Client) -> bool:
    """localStorage에서 로그인 정보 복구하여 자동 로그인"""
    import json, base64

    st.markdown("""
    <script>
    const auth = localStorage.getItem('_app_auth');
    if (auth) {
      try {
        const data = JSON.parse(atob(auth));
        // localStorage에 저장된 정보가 있음을 표시
        window.__app_auth_data = data;
      } catch (e) {
        localStorage.removeItem('_app_auth');
      }
    }
    </script>
    """, unsafe_allow_html=True)

    # localStorage에서 읽은 정보로 session_state 복구
    # (JavaScript로 읽어진 값이 있는지 확인)
    # 실제로는 Query String 또는 Cookie를 통해 정보 전달
    return False


def clear_auth_from_storage() -> None:
    """localStorage에서 로그인 정보 삭제"""
    st.markdown("""
    <script>
    localStorage.removeItem('_app_auth');
    sessionStorage.removeItem('_auth_restored');
    </script>
    """, unsafe_allow_html=True)
