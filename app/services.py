import csv
import io
import json
import re
from datetime import datetime, timezone
from typing import Any

from .db import db, execute, row, rows


VALID_STATUSES = {"WAITING", "CALLED", "IN_SERVICE", "MISSED", "DONE", "CANCELLED"}


def parse_study_duration(value: Any) -> int | None:
    if value is None:
        return None
    s = str(value).strip().lower()
    if not s:
        return None
    if "2" in s or "дв" in s or "two" in s:
        return 2
    if "3" in s or "тр" in s or "three" in s:
        return 3
    if "4" in s or "чет" in s or "four" in s:
        return 4
    try:
        n = int(float(s))
        return n if n in {2, 3, 4} else None
    except ValueError:
        return None


def parse_course(value: Any) -> int | None:
    m = re.search(r"\d+", str(value or ""))
    if not m:
        return None
    n = int(m.group(0))
    return n if 1 <= n <= 4 else None


def format_queue_number(n: Any) -> str:
    return str(int(n or 0)).zfill(3)


def parse_ymd(value: Any) -> str | None:
    s = str(value or "").strip()
    return s if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s) else None


def count_words(text: Any) -> int:
    return len([x for x in re.split(r"\s+", str(text or "").strip()) if x])


def json_list(raw: Any, default: list[Any] | None = None) -> list[Any]:
    if raw is None or raw == "":
        return default or []
    if isinstance(raw, list):
        return raw
    try:
        val = json.loads(str(raw))
        return val if isinstance(val, list) else (default or [])
    except Exception:
        return default or []


def normalize(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def parse_school_scopes(raw: Any) -> dict[str, dict[str, list[Any] | None]]:
    if not raw:
        return {}
    try:
        obj = raw if isinstance(raw, dict) else json.loads(str(raw))
    except Exception:
        return {}
    if not isinstance(obj, dict):
        return {}
    out: dict[str, dict[str, list[Any] | None]] = {}
    for school, cfg in obj.items():
        if not isinstance(cfg, dict):
            continue
        langs = [str(x).lower() for x in cfg.get("langs", []) if str(x).strip()]
        years = [parse_study_duration(x) for x in cfg.get("studyYears", [])]
        courses = [parse_course(x) for x in cfg.get("courses", [])]
        specs = [str(x) for x in cfg.get("specialtyCodes", []) if str(x)]
        out[str(school)] = {
            "langs": langs or None,
            "studyYears": [x for x in years if x is not None] or None,
            "courses": [x for x in courses if x is not None] or None,
            "specialtyCodes": specs or None,
        }
    return out


def ticket_matches_scope(ticket: dict[str, Any], scope: dict[str, Any]) -> bool:
    schools = [str(x) for x in json_list(scope.get("assigned_schools_json"), [])]
    langs_raw = json_list(scope.get("assigned_languages_json"), [])
    langs = [str(x).lower() for x in langs_raw] or None
    courses = [parse_course(x) for x in json_list(scope.get("assigned_courses_json"), [1, 2, 3, 4])]
    courses = [x for x in courses if x is not None] or [1, 2, 3, 4]
    specs_raw = json_list(scope.get("assigned_specialties_json"), [])
    specs = [str(x) for x in specs_raw] or None
    years_raw = json_list(scope.get("assigned_study_years_json"), [])
    years = [parse_study_duration(x) for x in years_raw]
    years = [x for x in years if x is not None] or None
    per_school = parse_school_scopes(scope.get("assigned_school_scopes_json"))

    school = str(ticket.get("school") or ticket.get("faculty") or "")
    if schools and normalize(school) not in {normalize(x) for x in schools}:
        return False

    scoped = next((cfg for k, cfg in per_school.items() if normalize(k) == normalize(school)), None)
    if scoped:
        langs = scoped.get("langs") or langs
        years = scoped.get("studyYears") or years
        courses = scoped.get("courses") or courses
        specs = scoped.get("specialtyCodes") or specs

    if langs:
        lang = str(ticket.get("language_section") or "").lower()
        if lang not in langs and "any" not in langs:
            return False
    course = parse_course(ticket.get("course"))
    if course is None or course not in courses:
        return False
    if specs:
        code = str(ticket.get("specialty_code") or "")
        if not code or code not in specs:
            return False
    if years:
        dur = parse_study_duration(ticket.get("study_duration_years"))
        if dur is None or dur not in years:
            return False
    return True


def advisor_scope(advisor: dict[str, Any]) -> dict[str, Any]:
    return {
        "assigned_schools_json": advisor.get("assigned_schools_json") or "[]",
        "assigned_languages_json": advisor.get("assigned_languages_json"),
        "assigned_courses_json": advisor.get("assigned_courses_json") or "[1,2,3,4]",
        "assigned_specialties_json": advisor.get("assigned_specialties_json"),
        "assigned_study_years_json": advisor.get("assigned_study_years_json"),
        "assigned_school_scopes_json": advisor.get("assigned_school_scopes_json"),
    }


def advisors_for_routing() -> list[dict[str, Any]]:
    return rows(
        """SELECT id, reception_open, assigned_schools_json, assigned_languages_json, assigned_courses_json,
                  assigned_specialties_json, assigned_study_years_json, assigned_school_scopes_json
           FROM advisors"""
    )


def pick_route_advisor_id(ticket: dict[str, Any], advisors: list[dict[str, Any]] | None = None) -> int | None:
    best: int | None = None
    for a in advisors or advisors_for_routing():
        if int(a.get("reception_open") or 0) == 0:
            continue
        if not ticket_matches_scope(ticket, advisor_scope(a)):
            continue
        aid = int(a["id"])
        best = aid if best is None else min(best, aid)
    return best


def visible_advisor_ids(ticket: dict[str, Any], advisors: list[dict[str, Any]] | None = None) -> list[int]:
    out: list[int] = []
    for a in advisors or advisors_for_routing():
        if int(a.get("reception_open") or 0) == 0:
            continue
        if ticket_matches_scope(ticket, advisor_scope(a)):
            out.append(int(a["id"]))
    return out


def recompute_route_owners() -> None:
    waiting = rows("SELECT id, school, language_section, course, specialty_code, study_duration_years FROM tickets WHERE status = 'WAITING'")
    advisors = advisors_for_routing()
    for t in waiting:
        execute("UPDATE tickets SET route_advisor_id = ? WHERE id = ?", (pick_route_advisor_id(t, advisors), t["id"]))


def registration_open_for_student(body: dict[str, Any]) -> dict[str, bool]:
    pseudo = {
        "school": str(body.get("school") or "").strip(),
        "language_section": str(body.get("language_section") or "").strip(),
        "course": str(body.get("course") or "").strip(),
        "specialty_code": str(body.get("specialty_code") or "").strip(),
        "study_duration_years": parse_study_duration(body.get("study_duration_years")),
    }
    matches_any = False
    any_open = False
    for a in advisors_for_routing():
        if ticket_matches_scope(pseudo, advisor_scope(a)):
            matches_any = True
            any_open = any_open or int(a.get("reception_open") or 0) != 0
    return {"open": any_open, "matchesAny": matches_any}


def next_queue_number() -> int:
    r = row("SELECT COALESCE(MAX(queue_number), 0) AS m FROM tickets")
    return int(r["m"]) + 1


def parse_dt(value: Any) -> datetime | None:
    s = str(value or "").strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def booking_callable_now(value: Any) -> bool:
    if value is None or str(value).strip() == "":
        return True
    dt = parse_dt(value)
    if dt is None:
        return False
    return dt.timestamp() <= datetime.now(timezone.utc).timestamp()


def compute_estimated_minutes(ticket: dict[str, Any]) -> int:
    waiting = rows("SELECT * FROM tickets WHERE status = 'WAITING' ORDER BY queue_number ASC")
    ahead = [
        t for t in waiting
        if int(t["queue_number"]) < int(ticket["queue_number"])
        and str(t.get("school") or "") == str(ticket.get("school") or "")
        and str(t.get("language_section") or "").lower() == str(ticket.get("language_section") or "").lower()
        and parse_course(t.get("course")) == parse_course(ticket.get("course"))
        and str(t.get("specialty_code") or "") == str(ticket.get("specialty_code") or "")
    ]
    return max(3, len(ahead) * 7)


def get_queue_session() -> dict[str, Any]:
    r = row("SELECT id, is_active, created_at FROM queue_session WHERE id = 1")
    return {"id": r["id"], "is_active": bool(r["is_active"]), "created_at": r["created_at"]} if r else {"id": 1, "is_active": True}


def get_live_queue() -> dict[str, Any]:
    advisors = advisors_for_routing()
    tickets = rows(
        """SELECT id, queue_number, status, school, specialty, specialty_code, language_section, course,
                  study_duration_years, student_first_name, student_last_name, advisor_id, route_advisor_id,
                  advisor_name, advisor_desk, advisor_faculty, advisor_department, comment, case_type,
                  student_comment, preferred_slot_at, created_at
           FROM tickets
           WHERE status IN ('WAITING','CALLED','IN_SERVICE')
           ORDER BY CASE status WHEN 'WAITING' THEN 0 ELSE 1 END,
                    CASE WHEN status = 'WAITING' AND preferred_slot_at IS NOT NULL THEN preferred_slot_at ELSE '9999-12-31' END ASC,
                    queue_number ASC"""
    )
    out = []
    for t in tickets:
        t["formatted_number"] = format_queue_number(t["queue_number"])
        t["route_advisor_id"] = t.get("route_advisor_id") if t["status"] == "WAITING" else None
        t["visible_manager_ids"] = visible_advisor_ids(t, advisors) if t["status"] == "WAITING" else None
        out.append(t)
    return {"session": get_queue_session(), "tickets": out}


def insert_visit_log(ticket: dict[str, Any], is_repeat: bool) -> None:
    execute(
        """INSERT INTO ticket_visit_log (
             ticket_id, advisor_id, queue_number, status, student_first_name, student_last_name, school,
             specialty, language_section, course, created_at, called_at, started_at, finished_at,
             advisor_name, advisor_desk, comment, case_type, is_repeat
           ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            ticket.get("id"), ticket.get("advisor_id"), ticket.get("queue_number"), ticket.get("status"),
            ticket.get("student_first_name"), ticket.get("student_last_name"), ticket.get("school"),
            ticket.get("specialty"), ticket.get("language_section"), ticket.get("course"),
            ticket.get("created_at"), ticket.get("called_at"), ticket.get("started_at"), ticket.get("finished_at"),
            ticket.get("advisor_name"), ticket.get("advisor_desk"), ticket.get("comment"), ticket.get("case_type"),
            1 if is_repeat else 0,
        ),
    )


def minutes_between(a: Any, b: Any) -> int | None:
    da = parse_dt(a)
    db_ = parse_dt(b)
    if not da or not db_:
        return None
    mins = (db_.timestamp() - da.timestamp()) / 60
    if mins < 0:
        return None
    return 1 if 0 < mins < 1 else round(mins)


def csv_response(rows_in: list[dict[str, Any]], fields: list[str]) -> str:
    f = io.StringIO()
    w = csv.writer(f, delimiter=";", lineterminator="\r\n")
    w.writerow(fields)
    for r in rows_in:
        w.writerow([r.get(k, "") for k in fields])
    return "\ufeff" + f.getvalue()


def today_sql() -> str:
    return row("SELECT date('now', 'localtime') AS d")["d"]
