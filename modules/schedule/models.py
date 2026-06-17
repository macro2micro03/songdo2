"""Schedule-specific table definitions and queries.

Note: actual CREATE TABLE is in db/migrations.py.
This file holds query constants and data validation.
"""
from supabase import Client
from config import TIME_SLOTS


def generate_time_slots():
    return list(TIME_SLOTS)


def check_conflict(con: Client, project_id, schedule_date, time_from, time_to, exclude_id=None):
    """Check if a time slot conflicts with existing schedules.

    Returns a list of conflicting schedule dicts. Empty list means no conflict.
    """
    q = (con.table("schedules").select("*")
         .eq("project_id", project_id).eq("schedule_date", schedule_date)
         .lt("time_from", time_to).gt("time_to", time_from))
    if exclude_id:
        q = q.neq("id", exclude_id)
    res = q.execute()
    return res.data or []
