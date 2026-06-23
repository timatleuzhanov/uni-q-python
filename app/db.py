import sqlite3
from pathlib import Path
from typing import Any

import bcrypt

from .config import SQLITE_PATH


def connect(path: Path = SQLITE_PATH) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


db = connect()


def rows(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return [dict(r) for r in db.execute(sql, params).fetchall()]


def row(sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    r = db.execute(sql, params).fetchone()
    return dict(r) if r else None


def execute(sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Cursor:
    cur = db.execute(sql, params)
    db.commit()
    return cur


def executemany(sql: str, seq: list[tuple[Any, ...]]) -> None:
    db.executemany(sql, seq)
    db.commit()


def bcrypt_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=10)).decode("utf-8")


def bcrypt_check(password: str, hashed: str | None) -> bool:
    if not hashed:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def has_column(table: str, name: str) -> bool:
    return any(r["name"] == name for r in rows(f"PRAGMA table_info({table})"))


def migrate() -> None:
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS queue_session (
          id INTEGER PRIMARY KEY,
          is_active INTEGER NOT NULL DEFAULT 1,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS advisors (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          name TEXT NOT NULL,
          faculty TEXT,
          department TEXT,
          desk_number TEXT,
          login TEXT UNIQUE,
          password_hash TEXT,
          assigned_schools_json TEXT,
          assigned_language TEXT,
          assigned_languages_json TEXT,
          assigned_courses_json TEXT,
          assigned_specialties_json TEXT,
          assigned_study_years_json TEXT,
          assigned_school_scopes_json TEXT,
          reception_open INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS tickets (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          queue_number INTEGER NOT NULL,
          status TEXT NOT NULL DEFAULT 'WAITING',
          student_first_name TEXT,
          student_last_name TEXT,
          school TEXT,
          specialty TEXT,
          specialty_code TEXT,
          language_section TEXT,
          course TEXT,
          study_duration_years INTEGER,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          called_at TEXT,
          started_at TEXT,
          finished_at TEXT,
          advisor_id INTEGER,
          route_advisor_id INTEGER,
          advisor_name TEXT,
          advisor_desk TEXT,
          advisor_faculty TEXT,
          advisor_department TEXT,
          comment TEXT,
          case_type TEXT,
          case_subtype TEXT,
          contact_type TEXT,
          student_comment TEXT,
          manager_attachment_name TEXT,
          manager_attachment_data_url TEXT,
          send_email_requested INTEGER,
          preferred_slot_at TEXT,
          missed_student_note TEXT
        );
        CREATE TABLE IF NOT EXISTS admin_users (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          login TEXT UNIQUE NOT NULL,
          password_hash TEXT NOT NULL,
          name TEXT
        );
        CREATE TABLE IF NOT EXISTS advisor_work_totals (
          advisor_id INTEGER PRIMARY KEY,
          total_ms INTEGER NOT NULL DEFAULT 0,
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS advisor_work_daily (
          advisor_id INTEGER NOT NULL,
          day TEXT NOT NULL,
          work_ms INTEGER NOT NULL DEFAULT 0,
          PRIMARY KEY (advisor_id, day),
          FOREIGN KEY (advisor_id) REFERENCES advisors(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS ticket_reviews (
          ticket_id INTEGER PRIMARY KEY,
          stars INTEGER NOT NULL,
          comment TEXT,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          FOREIGN KEY (ticket_id) REFERENCES tickets(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS stats_events (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          event_type TEXT NOT NULL,
          meta TEXT,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS ticket_visit_log (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          ticket_id INTEGER NOT NULL,
          advisor_id INTEGER,
          queue_number INTEGER NOT NULL,
          status TEXT NOT NULL,
          student_first_name TEXT,
          student_last_name TEXT,
          school TEXT,
          specialty TEXT,
          language_section TEXT,
          course TEXT,
          created_at TEXT,
          called_at TEXT,
          started_at TEXT,
          finished_at TEXT,
          advisor_name TEXT,
          advisor_desk TEXT,
          comment TEXT,
          case_type TEXT,
          is_repeat INTEGER NOT NULL DEFAULT 0,
          FOREIGN KEY (ticket_id) REFERENCES tickets(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS chat_feedback (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          user_question TEXT,
          user_question_norm TEXT,
          answer_text TEXT,
          kb_question_norm TEXT,
          source TEXT,
          helpful INTEGER NOT NULL
        );
        """
    )
    for table, cols in {
        "tickets": {
            "preferred_slot_at": "TEXT",
            "missed_student_note": "TEXT",
            "student_comment": "TEXT",
            "study_duration_years": "INTEGER",
            "route_advisor_id": "INTEGER",
            "manager_attachment_name": "TEXT",
            "manager_attachment_data_url": "TEXT",
            "send_email_requested": "INTEGER",
            "case_subtype": "TEXT",
            "contact_type": "TEXT",
        },
        "advisors": {
            "reception_open": "INTEGER NOT NULL DEFAULT 1",
            "assigned_study_years_json": "TEXT",
            "assigned_school_scopes_json": "TEXT",
        },
    }.items():
        for col, typ in cols.items():
            if not has_column(table, col):
                db.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")
    db.commit()


def seed() -> None:
    if not row("SELECT 1 FROM queue_session WHERE id = 1"):
        execute("INSERT INTO queue_session (id, is_active) VALUES (1, 1)")
    for login, password, name in [
        ("S.Mussa@almau.edu.kz", "admin2026", "Мұса Самал"),
        ("g.duisenbek@almau.edu.kz", "admin2026", "Дүйсенбек Гүлсана Мұханқызы"),
    ]:
        if not row("SELECT 1 FROM admin_users WHERE login = ?", (login,)):
            execute("INSERT INTO admin_users (login, password_hash, name) VALUES (?, ?, ?)", (login, bcrypt_hash(password), name))
    for login, password, name in [
        ("d.aubakirova@almau.edu.kz", "almau2026", "Аубакирова Дамира"),
        ("s.kussainova@almau.edu.kz", "almau2026", "Кусайнова Шолпан"),
        ("s.akhmetova@almau.edu.kz", "almau2026", "Ахметова Салтанат"),
        ("a.omar@almau.edu.kz", "almau2026", "Омар Айдана"),
        ("a.zhauynger@almau.edu.kz", "almau2026", "Жауынгер Әлия"),
    ]:
        if not row("SELECT 1 FROM advisors WHERE login = ?", (login,)):
            execute(
                """INSERT INTO advisors (
                     name, faculty, department, desk_number, login, password_hash,
                     assigned_schools_json, assigned_language, assigned_languages_json,
                     assigned_courses_json, assigned_specialties_json, assigned_study_years_json, reception_open
                   ) VALUES (?, NULL, NULL, NULL, ?, ?, '[]', NULL, NULL, '[1,2,3,4]', NULL, NULL, 1)""",
                (name, login, bcrypt_hash(password)),
            )


migrate()
seed()
