from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable

import pandas as pd


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = BASE_DIR / "uploads"
DB_PATH = DATA_DIR / "project_management.db"
SCHEMA_PATH = BASE_DIR / "schema.sql"


STATUS_TYPES = ["Not Started", "In Progress", "Done", "At Risk", "Delayed", "Closed"]
USER_ROLES = ["Admin", "Project Director", "Project Manager", "Engineer", "Contractor", "Client Viewer"]

PV_SCHEDULE_TEMPLATE = [
    ("Site survey and pre-com report", 3),
    ("Drawing submission and approval", 14),
    ("Submit safety documents and approval", 14),
    ("SCDF (MAA) Submission", 14),
    ("Install Cat Ladder and Lifeline", 14),
    ("Materials Purchasing and Arrival", 30),
    ("Mobilisation & Site preparation", 7),
    ("Structure and Panel Installation", 30),
    ("Electrical Installation works", 21),
    ("Electrical shut down", 1),
    ("PV system Turn on", 1),
]


PROJECT_DEFAULTS = {
    "project_director": "Portfolio Director",
    "portfolio": "Engineering",
    "template_name": "Standard Project",
    "priority": "Medium",
    "baseline_start": None,
    "baseline_finish": None,
    "actual_start": None,
    "actual_finish": None,
    "budget": 0,
    "actual_cost": 0,
    "forecast_cost": 0,
    "health_score": 80,
}

TASK_DEFAULTS = {
    "parent_task_id": None,
    "baseline_start": None,
    "baseline_finish": None,
    "actual_start": None,
    "weight": 1,
    "dependency_ids": "",
    "is_critical": 0,
}


def ensure_directories() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    UPLOAD_DIR.mkdir(exist_ok=True)


@contextmanager
def get_connection():
    ensure_directories()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(seed: bool = True) -> None:
    ensure_directories()
    with get_connection() as conn:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        migrate_existing_database(conn)
        if seed and is_empty(conn, "projects"):
            seed_sample_data(conn)
        elif seed:
            enrich_existing_database(conn)
        recalculate_all_project_progress(conn)


def migrate_existing_database(conn: sqlite3.Connection) -> None:
    rebuild_legacy_status_tables(conn)
    for table, defaults in {
        "projects": PROJECT_DEFAULTS,
        "tasks": TASK_DEFAULTS,
        "team_members": {"user_role": "Engineer", "capacity_hours": 40, "allocated_hours": 32},
        "schedules": {"baseline_start": None, "baseline_finish": None},
        "risk_logs": {"category": "Project", "probability": "Medium", "due_date": None},
        "documents": {"folder": "General", "version": "v1"},
    }.items():
        add_missing_columns(conn, table, defaults)


def rebuild_legacy_status_tables(conn: sqlite3.Connection) -> None:
    schema_order = [
        "projects", "tasks", "team_members", "schedules", "risk_logs", "issues", "budget_items",
        "milestones", "authority_submissions", "documents", "meetings", "email_settings", "email_notifications",
    ]
    legacy_tables: list[str] = []
    for table in schema_order:
        row = conn.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)).fetchone()
        sql = row["sql"] if row else ""
        if not sql:
            continue
        if (
            "CHECK (status IN ('Not Started', 'In Progress', 'Done', 'At Risk'))" in sql
            or "projects_legacy_status" in sql
        ):
            legacy_tables.append(table)
    if not legacy_tables:
        return

    conn.commit()
    conn.execute("PRAGMA foreign_keys = OFF")
    legacy_names = {}
    for table in legacy_tables:
        legacy_name = f"{table}_legacy_rebuild"
        legacy_names[table] = legacy_name
        conn.execute(f"DROP TABLE IF EXISTS {legacy_name}")
        conn.execute(f"ALTER TABLE {table} RENAME TO {legacy_name}")

    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    for table in schema_order:
        if table not in legacy_names:
            continue
        legacy_name = legacy_names[table]
        old_cols = {row["name"] for row in conn.execute(f"PRAGMA table_info({legacy_name})").fetchall()}
        new_cols = [row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
        common_cols = [col for col in new_cols if col in old_cols]
        cols_sql = ", ".join(common_cols)
        conn.execute(f"INSERT INTO {table} ({cols_sql}) SELECT {cols_sql} FROM {legacy_name}")
        conn.execute(f"DROP TABLE {legacy_name}")
    conn.execute("PRAGMA foreign_keys = ON")


def enrich_existing_database(conn: sqlite3.Connection) -> None:
    """Populate new enterprise modules for older databases without replacing user projects."""
    if not is_empty(conn, "budget_items"):
        sync_project_financials(conn)
        return

    today = date.today()
    projects = conn.execute("SELECT id, project_name, project_manager, target_completion_date, status FROM projects ORDER BY id").fetchall()
    for index, project in enumerate(projects):
        project_id = int(project["id"])
        manager = project["project_manager"] or "Project Manager"
        base_budget = 250000 + (index * 85000)
        actual = round(base_budget * (0.35 + min(index, 3) * 0.12), 2)
        forecast = round(base_budget * (1.0 + (0.05 if project["status"] in ["At Risk", "Delayed"] else -0.02)), 2)
        conn.execute(
            """
            INSERT INTO budget_items (project_id, cost_code, category, budget, actual, committed, forecast, owner)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (project_id, f"PM-{project_id:03d}", "Delivery", base_budget, actual, round(actual * 1.18, 2), forecast, manager),
        )
        conn.execute(
            """
            UPDATE projects
            SET budget = CASE WHEN COALESCE(budget, 0) = 0 THEN ? ELSE budget END,
                actual_cost = CASE WHEN COALESCE(actual_cost, 0) = 0 THEN ? ELSE actual_cost END,
                forecast_cost = CASE WHEN COALESCE(forecast_cost, 0) = 0 THEN ? ELSE forecast_cost END
            WHERE id = ?
            """,
            (base_budget, actual, forecast, project_id),
        )
        conn.execute(
            """
            INSERT INTO milestones (project_id, milestone_name, due_date, baseline_date, status, owner)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (project_id, "Next project milestone", project["target_completion_date"], project["target_completion_date"], project["status"], manager),
        )
        conn.execute(
            """
            INSERT INTO meetings (project_id, meeting_date, title, attendees, decisions, actions)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (project_id, (today - timedelta(days=index + 1)).isoformat(), "Weekly project review", "Client, PM, engineering, construction", "Maintain current recovery plan.", "Update task owners before next review."),
        )
        if index == 0 or "solar" in project["project_name"].lower() or "pv" in project["project_name"].lower():
            for authority, offset, status in [
                ("JTC", 7, "In Progress"),
                ("BCA", -3, "Done"),
                ("SCDF", 12, "At Risk"),
                ("EMA", 18, "In Progress"),
                ("SP", 9, "In Progress"),
                ("LEW", 14, "At Risk"),
                ("QP", -1, "Done"),
            ]:
                conn.execute(
                    """
                    INSERT INTO authority_submissions (
                        project_id, authority, package_name, owner, target_date, status, reference_no, remarks
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (project_id, authority, f"{authority} project submission", manager, (today + timedelta(days=offset)).isoformat(), status, f"{authority}-{project_id:04d}", "Migrated tracker item for dashboard readiness."),
                )

    if is_empty(conn, "issues") and projects:
        first = projects[0]
        conn.execute(
            """
            INSERT INTO issues (project_id, title, severity, owner, status, resolution_plan, due_date, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (int(first["id"]), "Close dashboard setup actions", "Medium", first["project_manager"], "Open", "Review migrated budget, authority, and reporting data.", (today + timedelta(days=5)).isoformat(), datetime.now().isoformat(timespec="seconds")),
        )
    sync_project_financials(conn)


def sync_project_financials(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        """
        SELECT project_id, COALESCE(SUM(budget), 0) AS budget, COALESCE(SUM(actual), 0) AS actual, COALESCE(SUM(forecast), 0) AS forecast
        FROM budget_items
        GROUP BY project_id
        """
    ).fetchall()
    for row in rows:
        conn.execute(
            """
            UPDATE projects
            SET budget = CASE WHEN COALESCE(budget, 0) = 0 THEN ? ELSE budget END,
                actual_cost = CASE WHEN COALESCE(actual_cost, 0) = 0 THEN ? ELSE actual_cost END,
                forecast_cost = CASE WHEN COALESCE(forecast_cost, 0) = 0 THEN ? ELSE forecast_cost END
            WHERE id = ?
            """,
            (row["budget"], row["actual"], row["forecast"], row["project_id"]),
        )


def add_missing_columns(conn: sqlite3.Connection, table: str, defaults: dict[str, object]) -> None:
    existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    for column, default in defaults.items():
        if column in existing:
            continue
        column_type = "REAL" if isinstance(default, float) else "INTEGER" if isinstance(default, int) else "TEXT"
        default_sql = "" if default is None else f" DEFAULT {sql_literal(default)}"
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}{default_sql}")


def sql_literal(value: object) -> str:
    if isinstance(value, str):
        return "'" + value.replace("'", "''") + "'"
    return str(value)


def is_empty(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0


def query_df(sql: str, params: Iterable | None = None) -> pd.DataFrame:
    with get_connection() as conn:
        return pd.read_sql_query(sql, conn, params=params or [])


def execute(sql: str, params: Iterable | None = None) -> int:
    with get_connection() as conn:
        cur = conn.execute(sql, params or [])
        return int(cur.lastrowid)


def execute_many(sql: str, rows: list[tuple]) -> None:
    with get_connection() as conn:
        conn.executemany(sql, rows)


ALLOWED_UPDATE_COLUMNS = {
    "projects": {
        "project_name", "client_name", "project_manager", "project_director", "portfolio", "template_name",
        "priority", "start_date", "target_completion_date", "baseline_start", "baseline_finish",
        "actual_start", "actual_finish", "status", "progress", "budget", "actual_cost", "forecast_cost", "health_score",
    },
    "tasks": {
        "task_type", "task_name", "owner", "start_date", "due_date", "baseline_start", "baseline_finish",
        "actual_start", "actual_completion_date", "status", "progress", "weight", "dependency_ids", "is_critical", "remarks",
    },
    "schedules": {
        "activity_name", "planned_start", "planned_finish", "baseline_start", "baseline_finish",
        "actual_start", "actual_finish", "delay_days", "progress", "status", "remarks",
    },
    "milestones": {"milestone_name", "due_date", "baseline_date", "actual_date", "status", "owner"},
    "budget_items": {"cost_code", "category", "budget", "actual", "committed", "forecast", "owner"},
    "risk_logs": {"title", "category", "severity", "probability", "owner", "status", "mitigation_plan", "due_date"},
    "issues": {"title", "severity", "owner", "status", "resolution_plan", "due_date"},
    "authority_submissions": {
        "authority", "package_name", "owner", "target_date", "submitted_date", "approval_date",
        "status", "reference_no", "remarks",
    },
    "team_members": {"name", "role", "user_role", "email", "phone", "capacity_hours", "allocated_hours"},
}


def update_record(table: str, record_id: int, fields: dict[str, object]) -> None:
    if table not in ALLOWED_UPDATE_COLUMNS:
        raise ValueError(f"Unsupported table: {table}")
    clean = {key: normalize_value(value) for key, value in fields.items() if key in ALLOWED_UPDATE_COLUMNS[table]}
    if not clean:
        return

    with get_connection() as conn:
        before = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (record_id,)).fetchone()
        if before is None:
            raise ValueError(f"Record not found: {table} #{record_id}")
        assignments = ", ".join([f"{key} = ?" for key in clean])
        conn.execute(f"UPDATE {table} SET {assignments} WHERE id = ?", (*clean.values(), record_id))
        project_id = int(before["project_id"]) if "project_id" in before.keys() else int(record_id) if table == "projects" else None
        refresh_rollups(conn, table, project_id)


def insert_record(table: str, project_id: int, fields: dict[str, object]) -> int:
    if table not in ALLOWED_UPDATE_COLUMNS or table == "projects":
        raise ValueError(f"Unsupported table: {table}")
    clean = {key: normalize_value(value) for key, value in fields.items() if key in ALLOWED_UPDATE_COLUMNS[table]}
    clean["project_id"] = project_id
    with get_connection() as conn:
        columns = list(clean.keys())
        placeholders = ", ".join(["?"] * len(columns))
        cur = conn.execute(
            f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})",
            tuple(clean[column] for column in columns),
        )
        refresh_rollups(conn, table, project_id)
        return int(cur.lastrowid)


def delete_record(table: str, record_id: int) -> None:
    if table not in ALLOWED_UPDATE_COLUMNS:
        raise ValueError(f"Unsupported table: {table}")
    with get_connection() as conn:
        before = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (record_id,)).fetchone()
        if before is None:
            return
        project_id = int(before["project_id"]) if "project_id" in before.keys() else int(record_id) if table == "projects" else None
        conn.execute(f"DELETE FROM {table} WHERE id = ?", (record_id,))
        if table != "projects":
            refresh_rollups(conn, table, project_id)


def normalize_value(value: object) -> object:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, bool):
        return int(value)
    return value


def refresh_rollups(conn: sqlite3.Connection, table: str, project_id: int | None) -> None:
    if project_id is None:
        return
    if table == "tasks":
        update_project_progress(conn, project_id)
    if table == "budget_items":
        recalculate_project_financials(conn, project_id)


def recalculate_project_financials(conn: sqlite3.Connection, project_id: int) -> None:
    totals = conn.execute(
        """
        SELECT COALESCE(SUM(budget), 0) AS budget, COALESCE(SUM(actual), 0) AS actual, COALESCE(SUM(forecast), 0) AS forecast
        FROM budget_items
        WHERE project_id = ?
        """,
        (project_id,),
    ).fetchone()
    conn.execute(
        "UPDATE projects SET budget = ?, actual_cost = ?, forecast_cost = ? WHERE id = ?",
        (totals["budget"], totals["actual"], totals["forecast"], project_id),
    )


def sync_task_from_schedule(project_id: int, old_activity_name: str, fields: dict[str, object]) -> None:
    activity_name = str(fields.get("activity_name") or old_activity_name or "").strip()
    if not activity_name:
        return
    planned_start = normalize_value(fields.get("planned_start") or date.today())
    planned_finish = normalize_value(fields.get("planned_finish") or date.today())
    baseline_start = normalize_value(fields.get("baseline_start") or fields.get("planned_start") or date.today())
    baseline_finish = normalize_value(fields.get("baseline_finish") or fields.get("planned_finish") or date.today())
    actual_start = normalize_value(fields.get("actual_start")) if fields.get("actual_start") else None
    actual_finish = normalize_value(fields.get("actual_finish")) if fields.get("actual_finish") else None
    status = str(fields.get("status") or "Not Started")
    progress = int(fields.get("progress") or 0)
    remarks = str(fields.get("remarks") or "")

    with get_connection() as conn:
        existing = conn.execute(
            """
            SELECT id
            FROM tasks
            WHERE project_id = ?
              AND LOWER(TRIM(task_name)) IN (LOWER(TRIM(?)), LOWER(TRIM(?)))
            ORDER BY id
            LIMIT 1
            """,
            (project_id, old_activity_name or activity_name, activity_name),
        ).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE tasks
                SET task_type = 'Major',
                    task_name = ?,
                    start_date = ?,
                    due_date = ?,
                    baseline_start = ?,
                    baseline_finish = ?,
                    actual_start = ?,
                    actual_completion_date = ?,
                    status = ?,
                    progress = ?,
                    remarks = ?
                WHERE id = ?
                """,
                (
                    activity_name,
                    planned_start,
                    planned_finish,
                    baseline_start,
                    baseline_finish,
                    actual_start,
                    actual_finish,
                    status,
                    progress,
                    remarks,
                    int(existing["id"]),
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO tasks (
                    project_id, task_type, task_name, owner, start_date, due_date, baseline_start,
                    baseline_finish, actual_start, actual_completion_date, status, progress, weight,
                    dependency_ids, is_critical, remarks
                )
                VALUES (?, 'Major', ?, 'Schedule', ?, ?, ?, ?, ?, ?, ?, ?, 1, '', 0, ?)
                """,
                (
                    project_id,
                    activity_name,
                    planned_start,
                    planned_finish,
                    baseline_start,
                    baseline_finish,
                    actual_start,
                    actual_finish,
                    status,
                    progress,
                    remarks,
                ),
            )
        update_project_progress(conn, project_id)


def apply_project_schedule_template(project_id: int, replace: bool = False) -> int:
    with get_connection() as conn:
        project = conn.execute(
            "SELECT start_date FROM projects WHERE id = ?",
            (project_id,),
        ).fetchone()
        if project is None:
            raise ValueError(f"Project not found: {project_id}")
        start = pd_date(project["start_date"])
        if replace:
            conn.execute("DELETE FROM schedules WHERE project_id = ?", (project_id,))
        existing_names = {
            str(row["activity_name"]).strip().lower()
            for row in conn.execute("SELECT activity_name FROM schedules WHERE project_id = ?", (project_id,)).fetchall()
        }
        cursor_date = start
        inserted = 0
        for activity_name, duration_days in PV_SCHEDULE_TEMPLATE:
            finish = cursor_date + timedelta(days=max(duration_days - 1, 0))
            if activity_name.strip().lower() not in existing_names:
                conn.execute(
                    """
                    INSERT INTO schedules (
                        project_id, activity_name, planned_start, planned_finish, baseline_start,
                        baseline_finish, actual_start, actual_finish, delay_days, progress, status, remarks
                    )
                    VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, 0, 0, 'Not Started', '')
                    """,
                    (
                        project_id,
                        activity_name,
                        cursor_date.isoformat(),
                        finish.isoformat(),
                        cursor_date.isoformat(),
                        finish.isoformat(),
                    ),
                )
                inserted += 1
            cursor_date = finish + timedelta(days=1)
        return inserted


def delete_task_for_schedule(project_id: int, activity_name: str) -> None:
    if not activity_name:
        return
    with get_connection() as conn:
        conn.execute(
            """
            DELETE FROM tasks
            WHERE project_id = ?
              AND task_type = 'Major'
              AND LOWER(TRIM(task_name)) = LOWER(TRIM(?))
            """,
            (project_id, activity_name),
        )
        update_project_progress(conn, project_id)


def sync_schedule_from_task(project_id: int, old_task_name: str, fields: dict[str, object]) -> None:
    if str(fields.get("task_type") or "").strip() != "Major":
        return
    task_name = str(fields.get("task_name") or old_task_name or "").strip()
    if not task_name:
        return
    planned_start = normalize_value(fields.get("start_date") or date.today())
    planned_finish = normalize_value(fields.get("due_date") or date.today())
    baseline_start = normalize_value(fields.get("baseline_start") or fields.get("start_date") or date.today())
    baseline_finish = normalize_value(fields.get("baseline_finish") or fields.get("due_date") or date.today())
    actual_start = normalize_value(fields.get("actual_start")) if fields.get("actual_start") else None
    actual_finish = normalize_value(fields.get("actual_completion_date")) if fields.get("actual_completion_date") else None
    status = str(fields.get("status") or "Not Started")
    progress = int(fields.get("progress") or 0)
    remarks = str(fields.get("remarks") or "")

    with get_connection() as conn:
        existing = conn.execute(
            """
            SELECT id
            FROM schedules
            WHERE project_id = ?
              AND LOWER(TRIM(activity_name)) IN (LOWER(TRIM(?)), LOWER(TRIM(?)))
            ORDER BY id
            LIMIT 1
            """,
            (project_id, old_task_name or task_name, task_name),
        ).fetchone()
        delay_days = calculate_delay(pd_date(planned_finish), pd_date(actual_finish) if actual_finish else None)
        if existing:
            conn.execute(
                """
                UPDATE schedules
                SET activity_name = ?,
                    planned_start = ?,
                    planned_finish = ?,
                    baseline_start = ?,
                    baseline_finish = ?,
                    actual_start = ?,
                    actual_finish = ?,
                    delay_days = ?,
                    progress = ?,
                    status = ?,
                    remarks = ?
                WHERE id = ?
                """,
                (
                    task_name,
                    planned_start,
                    planned_finish,
                    baseline_start,
                    baseline_finish,
                    actual_start,
                    actual_finish,
                    delay_days,
                    progress,
                    status,
                    remarks,
                    int(existing["id"]),
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO schedules (
                    project_id, activity_name, planned_start, planned_finish, baseline_start,
                    baseline_finish, actual_start, actual_finish, delay_days, progress, status, remarks
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    task_name,
                    planned_start,
                    planned_finish,
                    baseline_start,
                    baseline_finish,
                    actual_start,
                    actual_finish,
                    delay_days,
                    progress,
                    status,
                    remarks,
                ),
            )


def delete_schedule_for_task(project_id: int, task_name: str) -> None:
    if not task_name:
        return
    with get_connection() as conn:
        conn.execute(
            """
            DELETE FROM schedules
            WHERE project_id = ?
              AND LOWER(TRIM(activity_name)) = LOWER(TRIM(?))
            """,
            (project_id, task_name),
        )


def ensure_schedules_for_major_tasks(project_id: int) -> int:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                t.task_name,
                t.start_date,
                t.due_date,
                t.baseline_start,
                t.baseline_finish,
                t.actual_start,
                t.actual_completion_date,
                t.status,
                t.progress,
                t.remarks,
                p.start_date AS project_start,
                p.target_completion_date AS project_finish
            FROM tasks t
            JOIN projects p ON p.id = t.project_id
            WHERE t.project_id = ?
              AND t.task_type = 'Major'
              AND NOT EXISTS (
                  SELECT 1
                  FROM schedules s
                  WHERE s.project_id = t.project_id
                    AND LOWER(TRIM(s.activity_name)) = LOWER(TRIM(t.task_name))
              )
            ORDER BY t.id
            """,
            (project_id,),
        ).fetchall()
        for row in rows:
            planned_start = row["start_date"] or row["project_start"]
            planned_finish = row["due_date"] or row["project_finish"]
            actual_finish = row["actual_completion_date"]
            conn.execute(
                """
                INSERT INTO schedules (
                    project_id, activity_name, planned_start, planned_finish, baseline_start,
                    baseline_finish, actual_start, actual_finish, delay_days, progress, status, remarks
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    row["task_name"],
                    planned_start,
                    planned_finish,
                    row["baseline_start"] or planned_start,
                    row["baseline_finish"] or planned_finish,
                    row["actual_start"],
                    actual_finish,
                    calculate_delay(pd_date(planned_finish), pd_date(actual_finish) if actual_finish else None),
                    int(row["progress"] or 0),
                    row["status"] or "Not Started",
                    row["remarks"] or "",
                ),
            )
        return len(rows)


def pd_date(value: object) -> date:
    if isinstance(value, date):
        return value
    return datetime.fromisoformat(str(value)).date()


def get_project_options() -> pd.DataFrame:
    return query_df(
        """
        SELECT id, project_name, client_name, status
        FROM projects
        ORDER BY
            CASE status WHEN 'At Risk' THEN 1 WHEN 'Delayed' THEN 2 WHEN 'In Progress' THEN 3 ELSE 4 END,
            project_name
        """
    )


def recalculate_all_project_progress(conn: sqlite3.Connection) -> None:
    projects = conn.execute("SELECT id FROM projects").fetchall()
    for row in projects:
        update_project_progress(conn, int(row["id"]))


def update_project_progress(conn: sqlite3.Connection, project_id: int) -> None:
    row = conn.execute(
        """
        SELECT
            COALESCE(SUM(CASE WHEN task_type = 'Major' THEN weight ELSE weight * 0.35 END * progress), 0) AS weighted_done,
            COALESCE(SUM(CASE WHEN task_type = 'Major' THEN weight ELSE weight * 0.35 END), 0) AS weighted_total
        FROM tasks
        WHERE project_id = ?
        """,
        (project_id,),
    ).fetchone()
    if row["weighted_total"]:
        progress = round(row["weighted_done"] / row["weighted_total"])
        conn.execute("UPDATE projects SET progress = ? WHERE id = ?", (int(progress), project_id))


def add_project(
    project_name: str,
    client_name: str,
    project_manager: str,
    start_date: date,
    target_completion_date: date,
    status: str,
    progress: int,
    project_director: str = "",
    portfolio: str = "Engineering",
    template_name: str = "Standard Project",
    priority: str = "Medium",
    budget: float = 0,
) -> int:
    return execute(
        """
        INSERT INTO projects (
            project_name, client_name, project_manager, project_director, portfolio, template_name,
            priority, start_date, target_completion_date, baseline_start, baseline_finish,
            actual_start, status, progress, budget, forecast_cost, health_score
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            project_name,
            client_name,
            project_manager,
            project_director or project_manager,
            portfolio,
            template_name,
            priority,
            start_date.isoformat(),
            target_completion_date.isoformat(),
            start_date.isoformat(),
            target_completion_date.isoformat(),
            start_date.isoformat() if status != "Not Started" else None,
            status,
            progress,
            float(budget),
            float(budget),
            85,
        ),
    )


def add_task(
    project_id: int,
    task_type: str,
    task_name: str,
    owner: str,
    start_date: date,
    due_date: date,
    actual_completion_date: date | None,
    status: str,
    progress: int,
    remarks: str,
    weight: float = 1,
    dependency_ids: str = "",
    is_critical: bool = False,
) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO tasks (
                project_id, task_type, task_name, owner, start_date, due_date,
                baseline_start, baseline_finish, actual_start, actual_completion_date,
                status, progress, weight, dependency_ids, is_critical, remarks
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_id,
                task_type,
                task_name,
                owner,
                start_date.isoformat(),
                due_date.isoformat(),
                start_date.isoformat(),
                due_date.isoformat(),
                start_date.isoformat() if status != "Not Started" else None,
                actual_completion_date.isoformat() if actual_completion_date else None,
                status,
                progress,
                float(weight),
                dependency_ids,
                int(is_critical),
                remarks,
            ),
        )
        update_project_progress(conn, project_id)
        return int(cur.lastrowid)


def add_team_member(
    project_id: int,
    name: str,
    role: str,
    email: str,
    phone: str,
    user_role: str = "Engineer",
    capacity_hours: float = 40,
    allocated_hours: float = 32,
) -> int:
    return execute(
        """
        INSERT INTO team_members (project_id, name, role, user_role, email, phone, capacity_hours, allocated_hours)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (project_id, name, role, user_role, email, phone, capacity_hours, allocated_hours),
    )


def add_schedule(
    project_id: int,
    activity_name: str,
    planned_start: date,
    planned_finish: date,
    actual_start: date | None,
    actual_finish: date | None,
    progress: int,
    status: str,
    remarks: str,
) -> int:
    delay_days = calculate_delay(planned_finish, actual_finish)
    return execute(
        """
        INSERT INTO schedules (
            project_id, activity_name, planned_start, planned_finish, baseline_start, baseline_finish,
            actual_start, actual_finish, delay_days, progress, status, remarks
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            project_id,
            activity_name,
            planned_start.isoformat(),
            planned_finish.isoformat(),
            planned_start.isoformat(),
            planned_finish.isoformat(),
            actual_start.isoformat() if actual_start else None,
            actual_finish.isoformat() if actual_finish else None,
            delay_days,
            progress,
            status,
            remarks,
        ),
    )


def calculate_delay(planned_finish: date, actual_finish: date | None) -> int:
    if not actual_finish:
        return 0
    return max((actual_finish - planned_finish).days, 0)


def add_risk(
    project_id: int,
    title: str,
    severity: str,
    owner: str,
    status: str,
    mitigation_plan: str,
    category: str = "Project",
    probability: str = "Medium",
    due_date: date | None = None,
) -> int:
    return execute(
        """
        INSERT INTO risk_logs (project_id, title, category, severity, probability, owner, status, mitigation_plan, due_date, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            project_id,
            title,
            category,
            severity,
            probability,
            owner,
            status,
            mitigation_plan,
            due_date.isoformat() if due_date else None,
            datetime.now().isoformat(timespec="seconds"),
        ),
    )


def add_issue(project_id: int, title: str, severity: str, owner: str, status: str, resolution_plan: str, due_date: date | None) -> int:
    return execute(
        """
        INSERT INTO issues (project_id, title, severity, owner, status, resolution_plan, due_date, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (project_id, title, severity, owner, status, resolution_plan, due_date.isoformat() if due_date else None, datetime.now().isoformat(timespec="seconds")),
    )


def add_milestone(project_id: int, milestone_name: str, due_date: date, status: str, owner: str) -> int:
    return execute(
        """
        INSERT INTO milestones (project_id, milestone_name, due_date, baseline_date, status, owner)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (project_id, milestone_name, due_date.isoformat(), due_date.isoformat(), status, owner),
    )


def add_authority_submission(
    project_id: int,
    authority: str,
    package_name: str,
    owner: str,
    target_date: date,
    status: str,
    reference_no: str,
    remarks: str,
) -> int:
    return execute(
        """
        INSERT INTO authority_submissions (
            project_id, authority, package_name, owner, target_date, status, reference_no, remarks
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (project_id, authority, package_name, owner, target_date.isoformat(), status, reference_no, remarks),
    )


def add_budget_item(project_id: int, cost_code: str, category: str, budget: float, actual: float, committed: float, forecast: float, owner: str) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO budget_items (project_id, cost_code, category, budget, actual, committed, forecast, owner)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (project_id, cost_code, category, budget, actual, committed, forecast, owner),
        )
        recalculate_project_financials(conn, project_id)
        return int(cur.lastrowid)


def log_document(project_id: int, file_name: str, file_path: str, uploaded_by: str, folder: str = "General", version: str = "v1") -> int:
    return execute(
        """
        INSERT INTO documents (project_id, folder, file_name, version, file_path, uploaded_by, uploaded_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (project_id, folder, file_name, version, file_path, uploaded_by, datetime.now().isoformat(timespec="seconds")),
    )


def save_email_settings(sender_email: str, receiver_email: str, smtp_server: str, smtp_port: int, use_tls: bool) -> int:
    execute("UPDATE email_settings SET is_active = 0")
    return execute(
        """
        INSERT INTO email_settings (
            sender_email, receiver_email, smtp_server, smtp_port, use_tls, is_active, updated_at
        )
        VALUES (?, ?, ?, ?, ?, 1, ?)
        """,
        (sender_email, receiver_email, smtp_server, smtp_port, int(use_tls), datetime.now().isoformat(timespec="seconds")),
    )


def get_email_settings() -> pd.DataFrame:
    return query_df("SELECT * FROM email_settings WHERE is_active = 1 ORDER BY updated_at DESC LIMIT 1")


def log_email_notification(task_id: int | None, receiver: str, subject: str, body: str, status: str, error_message: str = "") -> None:
    execute(
        """
        INSERT INTO email_notifications (
            task_id, receiver_email, subject, body, status, error_message, sent_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (task_id, receiver, subject, body, status, error_message, datetime.now().isoformat(timespec="seconds")),
    )


def seed_sample_data(conn: sqlite3.Connection) -> None:
    today = date.today()
    projects = [
        ("Solar PV Rooftop Expansion", "Ngee Ann Facilities", "Aung Min", "Grace Lee", "Solar PV", "Solar PV EPC", "High", today - timedelta(days=68), today + timedelta(days=45), "In Progress", 0, 1280000, 698000, 1215000, 84),
        ("Factory LV Switchboard Upgrade", "Orion Manufacturing", "Ye Min Hein", "Grace Lee", "Electrical", "M&E Upgrade", "Critical", today - timedelta(days=32), today + timedelta(days=20), "At Risk", 0, 420000, 238000, 455000, 62),
        ("Warehouse Fire Alarm Retrofit", "Zenith Logistics", "Mei Lin", "Daniel Koh", "Life Safety", "Compliance Retrofit", "Medium", today + timedelta(days=7), today + timedelta(days=78), "Not Started", 0, 315000, 0, 310000, 91),
        ("BESS Commissioning Package", "SunGrid Energy", "Ravi Kumar", "Daniel Koh", "Energy Storage", "Commissioning", "Medium", today - timedelta(days=104), today - timedelta(days=7), "Closed", 100, 760000, 742000, 742000, 96),
        ("SP Grid Interconnection Works", "BrightGrid Solar", "Sarah Tan", "Grace Lee", "Solar PV", "Grid Interconnection", "High", today - timedelta(days=82), today + timedelta(days=8), "Delayed", 0, 540000, 386000, 590000, 58),
    ]
    project_ids: list[int] = []
    for p in projects:
        cur = conn.execute(
            """
            INSERT INTO projects (
                project_name, client_name, project_manager, project_director, portfolio, template_name,
                priority, start_date, target_completion_date, baseline_start, baseline_finish,
                actual_start, status, progress, budget, actual_cost, forecast_cost, health_score
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (p[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7].isoformat(), p[8].isoformat(), p[7].isoformat(), p[8].isoformat(), p[7].isoformat(), p[9], p[10], p[11], p[12], p[13], p[14]),
        )
        project_ids.append(cur.lastrowid)

    task_rows = [
        (0, "Major", "Authority package: JTC, BCA, SCDF, EMA", "Aung Min", -60, -26, "Done", 100, 2.8, "", 1, "All initial authority packages submitted."),
        (0, "Major", "SP submission and LEW endorsement", "Mei Lin", -24, 8, "In Progress", 72, 2.2, "1", 1, "LEW comments under closeout."),
        (0, "Major", "PV module installation", "Ravi Kumar", -14, 22, "In Progress", 61, 3.5, "2", 1, "Zone B pending weekend access."),
        (0, "Daily", "String testing and IV curve record", "Ravi Kumar", -2, 3, "In Progress", 45, 0.8, "3", 0, "Test kit booked."),
        (1, "Major", "Switchboard fabrication approval", "Ye Min Hein", -30, -4, "At Risk", 48, 2.5, "", 1, "Vendor drawing revision pending."),
        (1, "Daily", "Temporary shutdown method statement", "Sarah Tan", -7, -1, "Delayed", 35, 0.9, "5", 1, "Client approval overdue."),
        (2, "Major", "Site survey and detector zoning", "Mei Lin", 7, 18, "Not Started", 0, 1.6, "", 0, "Start after access permit."),
        (3, "Major", "Battery inverter commissioning", "Ravi Kumar", -36, -10, "Done", 100, 3.0, "", 1, "SAT report signed."),
        (3, "Daily", "As-built documentation submission", "Aung Min", -8, 2, "In Progress", 88, 0.8, "8", 0, "Final PDF pack under review."),
        (4, "Major", "SP service connection energization", "Sarah Tan", -24, -3, "Delayed", 65, 2.6, "", 1, "SP witness slot moved by one week."),
        (4, "Major", "Commissioning and performance ratio test", "Ravi Kumar", -2, 10, "At Risk", 30, 2.0, "10", 1, "Dependent on energization."),
    ]
    for row in task_rows:
        start = today + timedelta(days=row[4])
        due = today + timedelta(days=row[5])
        actual = due - timedelta(days=1) if row[6] == "Done" else None
        conn.execute(
            """
            INSERT INTO tasks (
                project_id, task_type, task_name, owner, start_date, due_date, baseline_start, baseline_finish,
                actual_start, actual_completion_date, status, progress, weight, dependency_ids, is_critical, remarks
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (project_ids[row[0]], row[1], row[2], row[3], start.isoformat(), due.isoformat(), start.isoformat(), due.isoformat(), start.isoformat() if row[6] != "Not Started" else None, actual.isoformat() if actual else None, row[6], row[7], row[8], row[9], row[10], row[11]),
        )

    team_rows = [
        (0, "Aung Min", "Project Manager", "Project Manager", "aung.min@example.com", "+65 8000 1001", 40, 36),
        (0, "Ravi Kumar", "Site Engineer", "Engineer", "ravi.kumar@example.com", "+65 8000 1002", 40, 42),
        (0, "Mei Lin", "QP Coordinator", "Engineer", "mei.lin@example.com", "+65 8000 1005", 40, 30),
        (1, "Ye Min Hein", "Project Manager", "Project Manager", "ye.min@example.com", "+65 8000 1003", 40, 44),
        (1, "Sarah Tan", "Safety Coordinator", "Engineer", "sarah.tan@example.com", "+65 8000 1004", 40, 37),
        (2, "Mei Lin", "Project Manager", "Project Manager", "mei.lin@example.com", "+65 8000 1005", 40, 18),
        (3, "Ravi Kumar", "Commissioning Lead", "Engineer", "ravi.kumar@example.com", "+65 8000 1002", 40, 16),
        (4, "Sarah Tan", "Project Manager", "Project Manager", "sarah.tan@example.com", "+65 8000 1004", 40, 46),
    ]
    conn.executemany(
        """
        INSERT INTO team_members (project_id, name, role, user_role, email, phone, capacity_hours, allocated_hours)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [(project_ids[r[0]], *r[1:]) for r in team_rows],
    )

    schedule_rows = [
        (0, "Engineering and authority submissions", -68, -22, -67, -21, 1, 100, "Done", "Minor BCA clarification closed."),
        (0, "Procurement and delivery", -40, -5, -39, None, 0, 92, "In Progress", "Final inverters arriving this week."),
        (0, "Installation works", -15, 24, -13, None, 0, 60, "In Progress", "Additional weekend crew planned."),
        (1, "Equipment procurement", -32, 7, -31, None, 0, 38, "At Risk", "Supplier confirmation pending."),
        (2, "Authority submission", 15, 35, None, None, 0, 0, "Not Started", "Awaiting survey package."),
        (3, "Commissioning and handover", -25, -7, -24, -6, 1, 100, "Closed", "Closed with punch list accepted."),
        (4, "SP testing and energization", -18, -2, -17, None, 0, 68, "Delayed", "Witness test rescheduled."),
    ]
    for r in schedule_rows:
        ps = today + timedelta(days=r[2])
        pf = today + timedelta(days=r[3])
        ast = today + timedelta(days=r[4]) if r[4] is not None else None
        af = today + timedelta(days=r[5]) if r[5] is not None else None
        conn.execute(
            """
            INSERT INTO schedules (
                project_id, activity_name, planned_start, planned_finish, baseline_start, baseline_finish,
                actual_start, actual_finish, delay_days, progress, status, remarks
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (project_ids[r[0]], r[1], ps.isoformat(), pf.isoformat(), ps.isoformat(), pf.isoformat(), ast.isoformat() if ast else None, af.isoformat() if af else None, r[6], r[7], r[8], r[9]),
        )

    budget_rows = [
        (0, "PV-100", "Engineering", 120000, 86000, 94000, 116000, "Aung Min"),
        (0, "PV-200", "Procurement", 760000, 430000, 692000, 748000, "Mei Lin"),
        (0, "PV-300", "Construction", 400000, 182000, 298000, 351000, "Ravi Kumar"),
        (1, "LV-100", "Design", 55000, 47000, 52000, 58000, "Ye Min Hein"),
        (1, "LV-200", "Equipment", 260000, 151000, 284000, 292000, "Ye Min Hein"),
        (1, "LV-300", "Site Works", 105000, 40000, 76000, 105000, "Sarah Tan"),
        (4, "SP-100", "Testing", 180000, 124000, 168000, 205000, "Sarah Tan"),
        (4, "SP-200", "Commissioning", 360000, 262000, 330000, 385000, "Ravi Kumar"),
    ]
    conn.executemany(
        """
        INSERT INTO budget_items (project_id, cost_code, category, budget, actual, committed, forecast, owner)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [(project_ids[r[0]], *r[1:]) for r in budget_rows],
    )

    milestone_rows = [
        (0, "JTC/BCA/SCDF/EMA approval", 4, "In Progress", "Mei Lin"),
        (0, "PV installation complete", 22, "In Progress", "Ravi Kumar"),
        (1, "Client shutdown approval", -1, "Delayed", "Sarah Tan"),
        (2, "Survey package issued", 14, "Not Started", "Mei Lin"),
        (4, "SP energization", 6, "Delayed", "Sarah Tan"),
    ]
    conn.executemany(
        "INSERT INTO milestones (project_id, milestone_name, due_date, baseline_date, status, owner) VALUES (?, ?, ?, ?, ?, ?)",
        [(project_ids[r[0]], r[1], (today + timedelta(days=r[2])).isoformat(), (today + timedelta(days=r[2])).isoformat(), r[3], r[4]) for r in milestone_rows],
    )

    authority_rows = [
        (0, "JTC", "Rooftop PV installation notice", "Mei Lin", 3, "In Progress", "JTC-PV-24018", "Awaiting officer comments."),
        (0, "BCA", "Structural endorsement package", "Mei Lin", -9, "Done", "BCA-STR-1182", "Approved."),
        (0, "SCDF", "Fire safety clearance", "Aung Min", 12, "At Risk", "SCDF-FS-5581", "Hydrant access mark-up requested."),
        (0, "EMA", "Generation licence exemption", "Aung Min", 18, "In Progress", "EMA-GEN-8901", "Submitted through portal."),
        (0, "SP", "Grid connection and meter change", "Sarah Tan", 8, "In Progress", "SP-INT-7719", "LEW endorsement attached."),
        (4, "SP", "Witness testing", "Sarah Tan", -2, "Delayed", "SP-WT-5520", "SP slot rescheduled."),
        (4, "LEW", "LEW energization certificate", "Ravi Kumar", 7, "At Risk", "LEW-232", "Pending SP witness test."),
        (0, "QP", "QP structural declaration", "Mei Lin", -4, "Done", "QP-981", "Signed and filed."),
    ]
    conn.executemany(
        """
        INSERT INTO authority_submissions (
            project_id, authority, package_name, owner, target_date, status, reference_no, remarks
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [(project_ids[r[0]], r[1], r[2], r[3], (today + timedelta(days=r[4])).isoformat(), r[5], r[6], r[7]) for r in authority_rows],
    )

    risk_rows = [
        (0, "Wet weather delaying rooftop access", "Construction", "Medium", "Medium", "Aung Min", "Open", "Shift non-rooftop electrical works forward.", 6),
        (1, "Switchboard drawing approval delay", "Vendor", "High", "High", "Ye Min Hein", "Open", "Daily vendor escalation and temporary bypass plan.", 2),
        (4, "SP witness testing moved beyond planned energization", "Authority", "Critical", "High", "Sarah Tan", "Open", "Escalate with LEW and resequence commissioning crew.", 1),
        (3, "Final O&M document comments", "Documentation", "Low", "Low", "Ravi Kumar", "Monitoring", "Close after client document review.", 5),
    ]
    conn.executemany(
        """
        INSERT INTO risk_logs (
            project_id, title, category, severity, probability, owner, status, mitigation_plan, due_date, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [(project_ids[r[0]], r[1], r[2], r[3], r[4], r[5], r[6], r[7], (today + timedelta(days=r[8])).isoformat(), datetime.now().isoformat(timespec="seconds")) for r in risk_rows],
    )

    issue_rows = [
        (1, "Client method statement comments not closed", "High", "Sarah Tan", "Open", "Workshop with client reviewer and safety lead.", 1),
        (4, "Commissioning team standby cost increasing", "Medium", "Ravi Kumar", "Monitoring", "Confirm revised SP witness slot before booking night shift.", 2),
    ]
    conn.executemany(
        "INSERT INTO issues (project_id, title, severity, owner, status, resolution_plan, due_date, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [(project_ids[r[0]], r[1], r[2], r[3], r[4], r[5], (today + timedelta(days=r[6])).isoformat(), datetime.now().isoformat(timespec="seconds")) for r in issue_rows],
    )

    meeting_rows = [
        (0, today - timedelta(days=2), "Weekly PV coordination", "Client, PM, LEW, QP", "Weekend access approved for Zone B.", "Issue updated SCDF mark-up by Friday."),
        (1, today - timedelta(days=1), "Switchboard recovery meeting", "Client, vendor, PM", "Proceed with fabrication after redline approval.", "Vendor to return revised drawing within 24 hours."),
        (4, today - timedelta(days=3), "SP energization readiness", "SP, LEW, PM, commissioning lead", "Witness test moved to next available slot.", "Hold commissioning resources until slot confirmed."),
    ]
    conn.executemany(
        "INSERT INTO meetings (project_id, meeting_date, title, attendees, decisions, actions) VALUES (?, ?, ?, ?, ?, ?)",
        [(project_ids[r[0]], r[1].isoformat(), r[2], r[3], r[4], r[5]) for r in meeting_rows],
    )

    conn.execute(
        """
        INSERT INTO email_settings (
            sender_email, receiver_email, smtp_server, smtp_port, use_tls, is_active, updated_at
        )
        VALUES (?, ?, ?, ?, ?, 1, ?)
        """,
        ("pm.notifications@example.com", "project.team@example.com", "smtp.gmail.com", 587, 1, datetime.now().isoformat(timespec="seconds")),
    )
    recalculate_all_project_progress(conn)
