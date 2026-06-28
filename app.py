from __future__ import annotations

import smtplib
from datetime import date, datetime, timedelta
from email.message import EmailMessage
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

import database as db

try:
    from st_aggrid import AgGrid, GridOptionsBuilder
except Exception:  # pragma: no cover - optional dependency
    AgGrid = None
    GridOptionsBuilder = None


STATUSES = getattr(db, "STATUS_TYPES", ["Not Started", "In Progress", "Done", "At Risk", "Delayed", "Closed"])
USER_ROLES = getattr(db, "USER_ROLES", ["Admin", "Project Director", "Project Manager", "Engineer", "Contractor", "Client Viewer"])
STATUS_COLORS = {
    "Not Started": "#64748b",
    "In Progress": "#2563eb",
    "Done": "#16a34a",
    "At Risk": "#f59e0b",
    "Delayed": "#dc2626",
    "Closed": "#334155",
}
AUTHORITY_TYPES = ["JTC", "BCA", "SCDF", "EMA", "SP", "LEW", "QP", "Engineering", "Construction", "Commissioning"]
REPORT_TYPES = ["Weekly Report", "Monthly Report", "Executive Report", "Progress Report", "Cost Report", "Resource Report"]


st.set_page_config(
    page_title="Enterprise Project Management",
    page_icon=":clipboard:",
    layout="wide",
    initial_sidebar_state="expanded",
)


def apply_styles(theme: str) -> None:
    dark = theme == "Dark"
    st.markdown(
        f"""
        <style>
        :root {{
            --bg: {"#0b1220" if dark else "#f6f8fb"};
            --panel: {"#111827" if dark else "#ffffff"};
            --panel-2: {"#172033" if dark else "#f9fafb"};
            --ink: {"#f8fafc" if dark else "#0f172a"};
            --muted: {"#cbd5e1" if dark else "#64748b"};
            --border: {"#263244" if dark else "#d9e2ec"};
            --accent: #2563eb;
            --success: #16a34a;
            --warn: #f59e0b;
            --danger: #dc2626;
        }}
        .stApp {{ background: var(--bg); color: var(--ink); }}
        .block-container {{ padding-top: 1.15rem; padding-bottom: 3rem; max-width: 1500px; }}
        [data-testid="stSidebar"] {{
            background: {"#eef3f8" if dark else "#f4f7fb"};
            border-right: 1px solid {"#cbd5e1" if dark else "#d9e2ec"};
        }}
        [data-testid="stSidebar"] * {{ color: #1f2937; }}
        [data-testid="stSidebar"] .stCaption, [data-testid="stSidebar"] small {{ color: #64748b !important; }}
        [data-testid="stSidebar"] hr {{ border-color: #d9e2ec; }}
        [data-testid="stSidebar"] [data-baseweb="select"] > div,
        [data-testid="stSidebar"] [data-baseweb="input"] {{
            background: #ffffff;
            border-color: #cbd5e1;
            color: #111827;
        }}
        [data-testid="stSidebar"] [data-baseweb="tag"] {{
            background: #e8eef6;
            color: #1f2937;
        }}
        [data-testid="stSidebar"] [role="radiogroup"] label p {{ color: #1f2937 !important; }}
        h1, h2, h3 {{ color: var(--ink); letter-spacing: 0; }}
        div[data-testid="stMetric"] {{
            background: var(--panel);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: .85rem 1rem;
            box-shadow: 0 1px 2px rgba(15, 23, 42, .05);
        }}
        .metric-card, .panel {{
            background: var(--panel);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 1rem;
            box-shadow: 0 1px 2px rgba(15, 23, 42, .04);
        }}
        .metric-label {{
            color: var(--muted);
            font-size: .76rem;
            text-transform: uppercase;
            font-weight: 750;
        }}
        .metric-value {{
            color: var(--ink);
            font-size: 1.9rem;
            font-weight: 800;
            line-height: 1.15;
        }}
        .muted {{ color: var(--muted); }}
        .workspace-header {{
            background: var(--panel);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 1rem 1.15rem;
            margin-bottom: .8rem;
        }}
        .status-badge {{
            display: inline-block;
            padding: .22rem .58rem;
            border-radius: 999px;
            color: #ffffff;
            font-size: .78rem;
            font-weight: 750;
            white-space: nowrap;
        }}
        .small-title {{
            font-size: .95rem;
            font-weight: 800;
            margin: .25rem 0 .55rem;
            color: var(--ink);
        }}
        .stTabs [data-baseweb="tab-list"] {{ gap: .25rem; }}
        .stTabs [data-baseweb="tab"] {{
            border-radius: 8px;
            border: 1px solid var(--border);
            background: var(--panel);
            padding: .45rem .85rem;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def money(value: float | int | None) -> str:
    value = float(value or 0)
    if abs(value) >= 1_000_000:
        return f"${value / 1_000_000:.2f}M"
    if abs(value) >= 1_000:
        return f"${value / 1_000:.0f}K"
    return f"${value:,.0f}"


def metric_card(label: str, value: str, caption: str = "") -> None:
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-label">{label}</div>
            <div class="metric-value">{value}</div>
            <div class="muted" style="font-size:.86rem;">{caption}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def status_badge(status: str) -> str:
    return f'<span class="status-badge" style="background:{STATUS_COLORS.get(status, "#475569")};">{status}</span>'


def show_table(frame: pd.DataFrame, columns: list[str] | None = None, height: int = 360) -> None:
    view = frame.copy()
    if columns:
        view = view[[c for c in columns if c in view.columns]]
    if view.empty:
        st.info("No records found.")
        return
    if AgGrid and GridOptionsBuilder:
        gb = GridOptionsBuilder.from_dataframe(view)
        gb.configure_default_column(filter=True, sortable=True, resizable=True)
        gb.configure_pagination(paginationAutoPageSize=False, paginationPageSize=12)
        AgGrid(view, gridOptions=gb.build(), height=height, fit_columns_on_grid_load=True, theme="streamlit")
    else:
        st.dataframe(view, use_container_width=True, hide_index=True, height=height)


@st.cache_data(ttl=5)
def load_data() -> dict[str, pd.DataFrame]:
    return {
        "projects": db.query_df("SELECT * FROM projects ORDER BY target_completion_date"),
        "tasks": db.query_df(
            """
            SELECT t.*, p.project_name, p.client_name, p.portfolio
            FROM tasks t
            JOIN projects p ON p.id = t.project_id
            ORDER BY t.due_date
            """
        ),
        "team": db.query_df(
            """
            SELECT tm.*, p.project_name, p.portfolio
            FROM team_members tm
            JOIN projects p ON p.id = tm.project_id
            ORDER BY p.project_name, tm.role
            """
        ),
        "schedules": db.query_df(
            """
            SELECT s.*, p.project_name
            FROM schedules s
            JOIN projects p ON p.id = s.project_id
            ORDER BY s.planned_start
            """
        ),
        "risks": db.query_df(
            """
            SELECT r.*, p.project_name
            FROM risk_logs r
            JOIN projects p ON p.id = r.project_id
            ORDER BY CASE r.severity WHEN 'Critical' THEN 1 WHEN 'High' THEN 2 WHEN 'Medium' THEN 3 ELSE 4 END
            """
        ),
        "issues": db.query_df(
            """
            SELECT i.*, p.project_name
            FROM issues i
            JOIN projects p ON p.id = i.project_id
            ORDER BY i.due_date
            """
        ),
        "budget": db.query_df(
            """
            SELECT b.*, p.project_name, p.portfolio
            FROM budget_items b
            JOIN projects p ON p.id = b.project_id
            ORDER BY p.project_name, b.cost_code
            """
        ),
        "milestones": db.query_df(
            """
            SELECT m.*, p.project_name
            FROM milestones m
            JOIN projects p ON p.id = m.project_id
            ORDER BY m.due_date
            """
        ),
        "authority": db.query_df(
            """
            SELECT a.*, p.project_name
            FROM authority_submissions a
            JOIN projects p ON p.id = a.project_id
            ORDER BY a.target_date
            """
        ),
        "documents": db.query_df(
            """
            SELECT d.*, p.project_name
            FROM documents d
            JOIN projects p ON p.id = d.project_id
            ORDER BY d.uploaded_at DESC
            """
        ),
        "meetings": db.query_df(
            """
            SELECT m.*, p.project_name
            FROM meetings m
            JOIN projects p ON p.id = m.project_id
            ORDER BY m.meeting_date DESC
            """
        ),
        "notifications": db.query_df("SELECT * FROM email_notifications ORDER BY sent_at DESC LIMIT 100"),
    }


def refresh() -> None:
    load_data.clear()
    st.rerun()


def filter_data(data: dict[str, pd.DataFrame], portfolios: list[str], statuses: list[str]) -> dict[str, pd.DataFrame]:
    projects = data["projects"]
    if portfolios:
        projects = projects[projects["portfolio"].isin(portfolios)]
    if statuses:
        projects = projects[projects["status"].isin(statuses)]
    project_ids = set(projects["id"].tolist())
    filtered = {"projects": projects}
    for key, frame in data.items():
        if key == "projects":
            continue
        filtered[key] = frame[frame["project_id"].isin(project_ids)] if "project_id" in frame.columns else frame
    return filtered


def project_selector(data: dict[str, pd.DataFrame], label: str = "Project") -> tuple[int | None, pd.Series | None]:
    projects = data["projects"]
    if projects.empty:
        st.warning("Create a project first.")
        return None, None
    options = {f"{row.project_name} - {row.client_name}": int(row.id) for row in projects.itertuples()}
    selected = st.selectbox(label, list(options.keys()))
    project_id = options[selected]
    return project_id, projects[projects["id"] == project_id].iloc[0]


def date_value(value: object, fallback: date | None = None) -> date | None:
    if pd.isna(value) or value in ("", None):
        return fallback
    return pd.to_datetime(value).date()


def select_index(options: list[str], value: object) -> int:
    text = "" if pd.isna(value) else str(value)
    return options.index(text) if text in options else 0


def record_selector(frame: pd.DataFrame, label: str, name_col: str) -> pd.Series | None:
    if frame.empty:
        st.info(f"No {label.lower()} records to edit.")
        return None
    options = {
        f"#{int(row.id)} - {getattr(row, name_col)}": int(row.id)
        for row in frame.itertuples()
    }
    selected = st.selectbox(label, list(options.keys()))
    return frame[frame["id"] == options[selected]].iloc[0]


def delete_button(table: str, record_id: int, label: str, key: str) -> None:
    if st.form_submit_button(label, type="secondary"):
        db.delete_record(table, record_id)
        st.success("Record deleted.")
        refresh()


def clean_cell(value: object, default: object = "") -> object:
    if value is None or pd.isna(value):
        return default
    return value


def clean_text(value: object) -> str:
    return str(clean_cell(value, "")).strip()


def clean_int(value: object, default: int = 0) -> int:
    if value is None or pd.isna(value) or value == "":
        return default
    return int(float(value))


def clean_float(value: object, default: float = 0.0) -> float:
    if value is None or pd.isna(value) or value == "":
        return default
    return float(value)


def clean_bool(value: object) -> bool:
    if value is None or pd.isna(value):
        return False
    return bool(value)


def clean_date(value: object, fallback: date | None = None) -> date | None:
    if value is None or pd.isna(value) or value == "":
        return fallback
    return pd.to_datetime(value).date()


def prepare_editor_frame(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    if frame.empty:
        editor = pd.DataFrame(columns=["_delete", "id", *columns])
    else:
        editor = frame.copy()
        editor["_delete"] = False
        editor = editor[["_delete", "id", *[col for col in columns if col in editor.columns]]]
    return editor


def editor_common_config() -> dict:
    return {
        "_delete": st.column_config.CheckboxColumn("Delete"),
        "id": None,
    }


def portfolio_overview(data: dict[str, pd.DataFrame]) -> None:
    projects, tasks, team, milestones, budget = data["projects"], data["tasks"], data["team"], data["milestones"], data["budget"]
    today = pd.Timestamp(date.today())
    delayed_tasks = tasks[(pd.to_datetime(tasks["due_date"]) < today) & (~tasks["status"].isin(["Done", "Closed"]))]
    critical_tasks = tasks[(tasks["is_critical"] == 1) & (~tasks["status"].isin(["Done", "Closed"]))]
    active_projects = projects[projects["status"].isin(["In Progress", "At Risk", "Delayed"])]
    at_risk_projects = projects[projects["status"].eq("At Risk")]
    delayed_projects = projects[projects["status"].eq("Delayed")]
    upcoming_milestones = milestones[
        (pd.to_datetime(milestones["due_date"]) >= today)
        & (pd.to_datetime(milestones["due_date"]) <= today + pd.Timedelta(days=14))
        & (~milestones["status"].isin(["Done", "Closed"]))
    ] if not milestones.empty else milestones
    overall_progress = round(projects["progress"].mean()) if not projects.empty else 0
    budget_total = float(projects["budget"].sum()) if "budget" in projects else 0
    actual_total = float(projects["actual_cost"].sum()) if "actual_cost" in projects else 0
    utilization = round((team["allocated_hours"].sum() / team["capacity_hours"].sum()) * 100) if not team.empty and team["capacity_hours"].sum() else 0

    st.title("Projects Dashboard")
    st.caption("Executive portfolio overview across schedule, budget, risk, resources, approvals, and delivery health.")

    cols = st.columns(5)
    with cols[0]:
        metric_card("Total Projects", str(len(projects)), "Unlimited project register")
    with cols[1]:
        metric_card("Active Projects", str(len(active_projects)), "In progress, at risk, delayed")
    with cols[2]:
        metric_card("At Risk", str(len(at_risk_projects)), "Management attention")
    with cols[3]:
        metric_card("Delayed", str(len(delayed_projects)), "Schedule recovery needed")
    with cols[4]:
        metric_card("Overall Progress", f"{overall_progress}%", "Weighted from task progress")

    cols = st.columns(4)
    with cols[0]:
        st.metric("Budget", money(budget_total), f"Actual {money(actual_total)}")
    with cols[1]:
        st.metric("Cost Variance", money(budget_total - actual_total), "Budget minus actual")
    with cols[2]:
        st.metric("Upcoming Milestones", len(upcoming_milestones), "Next 14 days")
    with cols[3]:
        st.metric("Resource Utilization", f"{utilization}%", "Allocated / capacity")

    left, right = st.columns([1.05, 1])
    with left:
        status_counts = projects["status"].value_counts().rename_axis("status").reset_index(name="count")
        fig = px.bar(status_counts, x="status", y="count", color="status", color_discrete_map=STATUS_COLORS, title="Portfolio Status Mix")
        fig.update_layout(showlegend=False, margin=dict(t=45, l=10, r=10, b=10), yaxis_title="Projects", xaxis_title="")
        st.plotly_chart(fig, use_container_width=True)
    with right:
        fig = px.bar(
            projects.sort_values("progress"),
            x="progress",
            y="project_name",
            color="status",
            orientation="h",
            color_discrete_map=STATUS_COLORS,
            title="Progress by Project",
            labels={"progress": "Progress %", "project_name": ""},
        )
        fig.update_layout(margin=dict(t=45, l=10, r=10, b=10), xaxis_range=[0, 100])
        st.plotly_chart(fig, use_container_width=True)

    left, right = st.columns([1, 1])
    with left:
        if not budget.empty:
            budget_summary = budget.groupby("category", as_index=False)[["budget", "actual", "forecast"]].sum()
            fig = px.bar(
                budget_summary.melt("category", value_vars=["budget", "actual", "forecast"], var_name="type", value_name="amount"),
                x="category",
                y="amount",
                color="type",
                barmode="group",
                title="Budget vs Actual vs Forecast",
            )
            fig.update_layout(margin=dict(t=45, l=10, r=10, b=10), yaxis_title="Amount")
            st.plotly_chart(fig, use_container_width=True)
    with right:
        if not team.empty:
            utilization_df = team.assign(utilization=(team["allocated_hours"] / team["capacity_hours"] * 100).round(0))
            fig = px.bar(utilization_df, x="name", y="utilization", color="project_name", title="Resource Utilization")
            fig.add_hline(y=100, line_dash="dash", line_color="#dc2626")
            fig.update_layout(margin=dict(t=45, l=10, r=10, b=10), yaxis_title="Utilization %", xaxis_title="")
            st.plotly_chart(fig, use_container_width=True)

    tabs = st.tabs(["Upcoming Milestones", "Critical Tasks", "Delayed / Overdue", "Portfolio Register"])
    with tabs[0]:
        show_table(upcoming_milestones, ["project_name", "milestone_name", "owner", "due_date", "status"], 300)
    with tabs[1]:
        show_table(critical_tasks, ["project_name", "task_type", "task_name", "owner", "due_date", "status", "progress", "dependency_ids"], 300)
    with tabs[2]:
        show_table(delayed_tasks, ["project_name", "task_type", "task_name", "owner", "due_date", "status", "progress", "remarks"], 300)
    with tabs[3]:
        show_table(projects, ["project_name", "client_name", "portfolio", "project_manager", "priority", "status", "progress", "budget", "actual_cost", "health_score"], 340)


def project_workspace(data: dict[str, pd.DataFrame]) -> None:
    project_id, project = project_selector(data, "Open Project Workspace")
    if project_id is None or project is None:
        return
    p = project
    st.markdown(
        f"""
        <div class="workspace-header">
            <div class="metric-label">{p['portfolio']} / {p['client_name']}</div>
            <h2 style="margin:.15rem 0;">{p['project_name']}</h2>
            <div class="muted">Manager: {p['project_manager']} | Director: {p['project_director']} | Template: {p['template_name']} | {status_badge(p['status'])}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    tasks = data["tasks"][data["tasks"]["project_id"] == project_id]
    schedules = data["schedules"][data["schedules"]["project_id"] == project_id]
    if schedules.empty:
        created_schedule_rows = db.apply_project_schedule_template(project_id, replace=False)
        if created_schedule_rows:
            st.toast(f"Created {created_schedule_rows} schedule row(s) from the PV schedule template.")
            refresh()
    risks = data["risks"][data["risks"]["project_id"] == project_id]
    issues = data["issues"][data["issues"]["project_id"] == project_id]
    budget = data["budget"][data["budget"]["project_id"] == project_id]
    docs = data["documents"][data["documents"]["project_id"] == project_id]
    meetings = data["meetings"][data["meetings"]["project_id"] == project_id]
    team = data["team"][data["team"]["project_id"] == project_id]
    milestones = data["milestones"][data["milestones"]["project_id"] == project_id]

    tabs = st.tabs(["Overview", "Schedule", "Tasks", "Major Tasks", "Risks", "Issues", "Budget", "Documents", "Meetings", "Team"])
    with tabs[0]:
        cols = st.columns(5)
        with cols[0]:
            metric_card("Progress", f"{int(p['progress'])}%", "Automatic weighted calculation")
        with cols[1]:
            metric_card("Health", f"{int(p['health_score'])}", "Portfolio health score")
        with cols[2]:
            metric_card("Budget", money(p["budget"]), f"Actual {money(p['actual_cost'])}")
        with cols[3]:
            metric_card("Open Risks", str(len(risks[risks["status"].str.lower() != "closed"])), "Risk register")
        with cols[4]:
            metric_card("Critical Tasks", str(len(tasks[(tasks["is_critical"] == 1) & (~tasks["status"].isin(["Done", "Closed"]))])), "Active path")
        st.progress(int(p["progress"]) / 100, text=f"{int(p['progress'])}% complete")
        milestone_entry_form(project_id)
        if not milestones.empty:
            edit_milestone_form(milestones)
            show_table(milestones, ["milestone_name", "owner", "due_date", "baseline_date", "actual_date", "status"], 260)
    with tabs[1]:
        schedule_template_controls(project_id)
        schedule_spreadsheet_editor(project_id, schedules)
        show_gantt(schedules, tasks)
    with tabs[2]:
        default_task_type = "Major" if not tasks.empty and (tasks["task_type"].eq("Major").sum() >= tasks["task_type"].eq("Daily").sum()) else "Daily"
        task_spreadsheet_editor(project_id, tasks, "Task table - paste from Excel", default_task_type=default_task_type, default_owner=str(p["project_manager"]))
    with tabs[3]:
        majors = tasks[tasks["task_type"].eq("Major")]
        fig = px.bar(majors, x="task_name", y="progress", color="status", color_discrete_map=STATUS_COLORS, title="Major Task Weighted Progress") if not majors.empty else None
        if fig:
            fig.update_layout(xaxis_title="", yaxis_title="Progress %", yaxis_range=[0, 100])
            st.plotly_chart(fig, use_container_width=True)
        task_spreadsheet_editor(project_id, majors, "Major task table - paste from Excel", default_task_type="Major", default_owner=str(p["project_manager"]))
    with tabs[4]:
        risk_spreadsheet_editor(project_id, risks)
    with tabs[5]:
        issue_spreadsheet_editor(project_id, issues)
    with tabs[6]:
        budget_spreadsheet_editor(project_id, budget)
        if not budget.empty:
            fig = px.bar(
                budget.melt(["cost_code", "category"], value_vars=["budget", "actual", "committed", "forecast"], var_name="type", value_name="amount"),
                x="category",
                y="amount",
                color="type",
                barmode="group",
                title="Cost Breakdown",
            )
            st.plotly_chart(fig, use_container_width=True)
    with tabs[7]:
        show_upload_section(project_id, docs)
    with tabs[8]:
        show_table(meetings, ["meeting_date", "title", "attendees", "decisions", "actions"], 350)
    with tabs[9]:
        team_entry_form(project_id)
        edit_team_form(team)
        show_table(team, ["name", "role", "user_role", "email", "phone", "capacity_hours", "allocated_hours"], 350)


def schedule_template_controls(project_id: int) -> None:
    with st.expander("PV schedule template", expanded=False):
        st.caption("Template starts from the project start date and follows the standard PV schedule sequence.")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Add Missing Template Rows", type="primary", key=f"add_template_{project_id}"):
                inserted = db.apply_project_schedule_template(project_id, replace=False)
                st.success(f"Added {inserted} missing schedule row(s).")
                refresh()
        with c2:
            confirm_reset = st.checkbox("Replace current schedule", key=f"replace_schedule_confirm_{project_id}")
            if st.button("Reset From Project Start Date", disabled=not confirm_reset, key=f"reset_template_{project_id}"):
                inserted = db.apply_project_schedule_template(project_id, replace=True)
                st.success(f"Reset schedule with {inserted} template row(s).")
                refresh()


def show_gantt(schedules: pd.DataFrame, tasks: pd.DataFrame) -> None:
    if schedules.empty:
        st.info("No schedule or task records yet.")
        return
    show_schedule_matrix(schedules)
    gantt = schedules.rename(columns={"activity_name": "name", "planned_start": "start", "planned_finish": "finish"}).copy()
    gantt["record_type"] = "Schedule"
    gantt = gantt[["name", "start", "finish", "status", "progress", "record_type"]].copy()
    gantt["start"] = pd.to_datetime(gantt["start"], errors="coerce")
    gantt["finish"] = pd.to_datetime(gantt["finish"], errors="coerce")
    gantt = gantt.dropna(subset=["name", "start", "finish"])
    if gantt.empty:
        st.info("No schedule records have valid start and finish dates yet.")
        return
    min_start = gantt["start"].min() - pd.Timedelta(days=14)
    max_finish = gantt["finish"].max() + pd.Timedelta(days=30)
    chart_height = max(520, min(1100, 140 + len(gantt) * 28))
    fig = px.timeline(gantt, x_start="start", x_end="finish", y="name", color="status", color_discrete_map=STATUS_COLORS, hover_data=["progress", "record_type"], title="Baseline / Actual Schedule Gantt")
    fig.update_yaxes(autorange="reversed")
    fig.update_layout(
        margin=dict(t=55, l=10, r=80, b=35),
        yaxis_title="",
        height=chart_height,
        xaxis_range=[min_start, max_finish],
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    show_table(schedules, ["activity_name", "planned_start", "planned_finish", "baseline_start", "baseline_finish", "actual_start", "actual_finish", "delay_days", "progress", "status", "remarks"], 300)


def show_schedule_matrix(schedules: pd.DataFrame) -> None:
    frame = schedules.copy()
    frame["planned_start_dt"] = pd.to_datetime(frame["planned_start"], errors="coerce")
    frame["planned_finish_dt"] = pd.to_datetime(frame["planned_finish"], errors="coerce")
    frame = frame.dropna(subset=["activity_name", "planned_start_dt", "planned_finish_dt"])
    if frame.empty:
        return
    start_anchor = frame["planned_start_dt"].min()
    end_anchor = frame["planned_finish_dt"].max()
    week_count = max(12, min(52, int(((end_anchor - start_anchor).days // 7) + 2)))
    rows = []
    for item in frame.itertuples():
        duration_days = max((item.planned_finish_dt - item.planned_start_dt).days + 1, 1)
        row = {
            "Activity": item.activity_name,
            "Duration Weeks": max(1, int((duration_days + 6) // 7)),
            "_status": item.status,
        }
        for week in range(1, week_count + 1):
            week_start = start_anchor + pd.Timedelta(days=(week - 1) * 7)
            week_finish = week_start + pd.Timedelta(days=6)
            row[f"Week {week}"] = " " if item.planned_start_dt <= week_finish and item.planned_finish_dt >= week_start else ""
        rows.append(row)
    matrix = pd.DataFrame(rows)

    def style_schedule(value: object) -> str:
        if value == " ":
            return "background-color: #bfe3f2; border: 1px solid #9fb6c3;"
        return "border: 1px solid #d1d5db;"

    display = matrix.drop(columns=["_status"])
    week_cols = [col for col in display.columns if col.startswith("Week ")]
    styled = display.style.map(style_schedule, subset=week_cols).set_properties(
        subset=["Activity", "Duration Weeks"],
        **{"border": "1px solid #d1d5db", "font-weight": "600"},
    )
    st.markdown('<div class="small-title">Project Schedule Matrix</div>', unsafe_allow_html=True)
    st.dataframe(styled, use_container_width=True, hide_index=True, height=min(680, 120 + len(display) * 36))


def schedule_spreadsheet_editor(project_id: int, schedules: pd.DataFrame) -> None:
    with st.expander("Schedule table - paste from Excel", expanded=True):
        columns = [
            "activity_name", "planned_start", "planned_finish", "baseline_start", "baseline_finish",
            "actual_start", "actual_finish", "delay_days", "progress", "status", "remarks",
        ]
        editor = prepare_editor_frame(schedules, columns)
        for col in ["planned_start", "planned_finish", "baseline_start", "baseline_finish", "actual_start", "actual_finish"]:
            if col in editor:
                editor[col] = pd.to_datetime(editor[col], errors="coerce").dt.date
        if "status" in editor:
            editor["status"] = editor["status"].fillna("Not Started")
        if "progress" in editor:
            editor["progress"] = editor["progress"].fillna(0)
        if "delay_days" in editor:
            editor["delay_days"] = editor["delay_days"].fillna(0)

        edited = st.data_editor(
            editor,
            use_container_width=True,
            hide_index=True,
            height=420,
            num_rows="dynamic",
            key=f"schedule_sheet_{project_id}",
            column_config={
                **editor_common_config(),
                "activity_name": st.column_config.TextColumn("Activity Name"),
                "planned_start": st.column_config.DateColumn("Planned Start"),
                "planned_finish": st.column_config.DateColumn("Planned Finish"),
                "baseline_start": st.column_config.DateColumn("Baseline Start"),
                "baseline_finish": st.column_config.DateColumn("Baseline Finish"),
                "actual_start": st.column_config.DateColumn("Actual Start"),
                "actual_finish": st.column_config.DateColumn("Actual Finish"),
                "delay_days": st.column_config.NumberColumn("Delay Days", disabled=True),
                "progress": st.column_config.NumberColumn("Progress %", min_value=0, max_value=100),
                "status": st.column_config.SelectboxColumn("Status", options=STATUSES),
            },
        )
        unsaved_rows = edited[
            edited["id"].isna()
            & edited["activity_name"].apply(lambda value: bool(clean_text(value)))
        ] if "id" in edited.columns and "activity_name" in edited.columns else pd.DataFrame()
        if not unsaved_rows.empty:
            st.warning(f"{len(unsaved_rows)} new schedule row(s) are not saved yet. Click Save Schedule Table.")

        if st.button("Save Schedule Table", type="primary", key=f"save_schedule_sheet_{project_id}"):
            changed = 0
            skipped = 0
            for _, row in edited.iterrows():
                record_id = row.get("id")
                has_id = not pd.isna(record_id) if record_id is not None else False
                if clean_bool(row.get("_delete")) and has_id:
                    db.delete_record("schedules", int(record_id))
                    changed += 1
                    continue

                activity_name = clean_text(row.get("activity_name"))
                if not activity_name:
                    skipped += 1
                    continue
                planned_start = clean_date(row.get("planned_start"), date.today())
                planned_finish = clean_date(row.get("planned_finish"), planned_start or date.today())
                actual_finish = clean_date(row.get("actual_finish"))
                delay_days = db.calculate_delay(planned_finish, actual_finish) if planned_finish else 0
                fields = {
                    "activity_name": activity_name,
                    "planned_start": planned_start,
                    "planned_finish": planned_finish,
                    "baseline_start": clean_date(row.get("baseline_start"), planned_start),
                    "baseline_finish": clean_date(row.get("baseline_finish"), planned_finish),
                    "actual_start": clean_date(row.get("actual_start")),
                    "actual_finish": actual_finish,
                    "delay_days": delay_days,
                    "progress": clean_int(row.get("progress")),
                    "status": clean_text(row.get("status")) or "Not Started",
                    "remarks": clean_text(row.get("remarks")),
                }
                if has_id:
                    db.update_record("schedules", int(record_id), fields)
                else:
                    db.insert_record("schedules", project_id, fields)
                changed += 1
            st.success(f"Saved {changed} schedule change(s).")
            if skipped:
                st.warning(f"Skipped {skipped} row(s) without activity names.")
            refresh()


def project_setup(data: dict[str, pd.DataFrame]) -> None:
    st.title("Project Management")
    st.caption("Create unlimited projects from templates and add major/daily tasks, milestones, dependencies, and team allocations.")
    with st.form("project_form"):
        c1, c2, c3 = st.columns(3)
        project_name = c1.text_input("Project Name")
        client_name = c2.text_input("Client Name")
        template = c3.selectbox("Template", ["Standard Project", "Solar PV EPC", "M&E Upgrade", "Compliance Retrofit", "Commissioning", "Grid Interconnection"])
        c4, c5, c6 = st.columns(3)
        manager = c4.text_input("Project Manager")
        director = c5.text_input("Project Director")
        portfolio = c6.selectbox("Portfolio", ["Solar PV", "Electrical", "Life Safety", "Energy Storage", "Engineering", "Construction"])
        c7, c8, c9 = st.columns(3)
        start = c7.date_input("Start Date", value=date.today())
        target = c8.date_input("Target Completion", value=date.today() + timedelta(days=60))
        priority = c9.selectbox("Priority", ["Low", "Medium", "High", "Critical"])
        c10, c11, c12 = st.columns(3)
        status = c10.selectbox("Status", STATUSES)
        budget = c11.number_input("Initial Budget", min_value=0.0, value=250000.0, step=10000.0)
        progress = c12.slider("Initial Progress", 0, 100, 0)
        submitted = st.form_submit_button("Create Project", type="primary")
    if submitted:
        if not project_name or not client_name or not manager:
            st.error("Project name, client name, and project manager are required.")
        elif target < start:
            st.error("Target completion date cannot be before start date.")
        else:
            project_id = db.add_project(project_name, client_name, manager, start, target, status, progress, director, portfolio, template, priority, budget)
            db.add_team_member(project_id, manager, "Project Manager", "", "", "Project Manager", 40, 32)
            db.apply_project_schedule_template(project_id, replace=True)
            db.add_milestone(project_id, "Project completion", target, status, manager)
            st.success(f"Created project: {project_name}")
            refresh()
    edit_project_form(data["projects"])
    st.markdown('<div class="small-title">Project Register</div>', unsafe_allow_html=True)
    show_table(data["projects"], ["project_name", "client_name", "portfolio", "template_name", "project_manager", "priority", "status", "progress", "budget", "actual_cost"], 360)


def edit_project_form(projects: pd.DataFrame) -> None:
    with st.expander("Edit or delete existing project", expanded=False):
        row = record_selector(projects, "Project to edit", "project_name")
        if row is None:
            return
        with st.form(f"edit_project_{int(row['id'])}"):
            c1, c2, c3 = st.columns(3)
            project_name = c1.text_input("Project Name", value=str(row["project_name"]))
            client_name = c2.text_input("Client Name", value=str(row["client_name"]))
            template = c3.text_input("Template", value=str(row["template_name"]))
            c4, c5, c6 = st.columns(3)
            manager = c4.text_input("Project Manager", value=str(row["project_manager"]))
            director = c5.text_input("Project Director", value=str(row["project_director"]))
            portfolio = c6.text_input("Portfolio", value=str(row["portfolio"]))
            c7, c8, c9 = st.columns(3)
            start = c7.date_input("Start Date", value=date_value(row["start_date"], date.today()))
            target = c8.date_input("Target Completion", value=date_value(row["target_completion_date"], date.today()))
            priority_options = ["Low", "Medium", "High", "Critical"]
            priority = c9.selectbox("Priority", priority_options, index=select_index(priority_options, row["priority"]))
            c10, c11, c12 = st.columns(3)
            status = c10.selectbox("Status", STATUSES, index=select_index(STATUSES, row["status"]))
            budget = c11.number_input("Budget", min_value=0.0, value=float(row["budget"] or 0), step=10000.0)
            actual = c12.number_input("Actual Cost", min_value=0.0, value=float(row["actual_cost"] or 0), step=10000.0)
            c13, c14 = st.columns(2)
            forecast = c13.number_input("Forecast Cost", min_value=0.0, value=float(row["forecast_cost"] or 0), step=10000.0)
            health = c14.slider("Health Score", 0, 100, int(row["health_score"] or 0))
            save, delete = st.columns([1, 1])
            with save:
                saved = st.form_submit_button("Save Project", type="primary")
            with delete:
                deleted = st.form_submit_button("Delete Project", type="secondary")
        if saved:
            if target < start:
                st.error("Target completion date cannot be before start date.")
            elif not project_name or not client_name or not manager:
                st.error("Project name, client name, and project manager are required.")
            else:
                db.update_record(
                    "projects",
                    int(row["id"]),
                    {
                        "project_name": project_name,
                        "client_name": client_name,
                        "project_manager": manager,
                        "project_director": director,
                        "portfolio": portfolio,
                        "template_name": template,
                        "priority": priority,
                        "start_date": start,
                        "target_completion_date": target,
                        "status": status,
                        "budget": budget,
                        "actual_cost": actual,
                        "forecast_cost": forecast,
                        "health_score": health,
                    },
                )
                st.success("Project updated.")
                refresh()
        if deleted:
            db.delete_record("projects", int(row["id"]))
            st.success("Project deleted.")
            refresh()


def task_entry_form(project_id: int) -> None:
    with st.expander("Add task or dependency", expanded=False):
        with st.form(f"task_form_{project_id}"):
            c1, c2, c3 = st.columns([2, 1, 1])
            task_name = c1.text_input("Task Name")
            task_type = c2.selectbox("Task Type", ["Major", "Daily"])
            status = c3.selectbox("Status", STATUSES)
            c4, c5, c6 = st.columns(3)
            owner = c4.text_input("Owner")
            start = c5.date_input("Start Date", value=date.today())
            due = c6.date_input("Due Date", value=date.today() + timedelta(days=7))
            c7, c8, c9 = st.columns(3)
            progress = c7.slider("Progress %", 0, 100, 0)
            weight = c8.number_input("Weight", min_value=0.1, value=1.0, step=0.1)
            critical = c9.checkbox("Critical Task")
            dependencies = st.text_input("Dependency IDs", help="Comma-separated predecessor task IDs.")
            remarks = st.text_area("Remarks")
            submitted = st.form_submit_button("Add Task", type="primary")
        if submitted:
            if not task_name or not owner:
                st.error("Task name and owner are required.")
            elif due < start:
                st.error("Due date cannot be before start date.")
            else:
                db.add_task(project_id, task_type, task_name, owner, start, due, date.today() if status in ["Done", "Closed"] else None, status, progress, remarks, weight, dependencies, critical)
                st.success("Task added and project progress recalculated.")
                refresh()


def task_spreadsheet_editor(
    project_id: int,
    tasks: pd.DataFrame,
    title: str = "Task table - paste from Excel",
    default_task_type: str = "Daily",
    default_owner: str = "",
) -> None:
    editor_key = title.lower().replace(" ", "_").replace("-", "_")
    with st.expander(title, expanded=True):
        columns = ["task_type", "task_name", "owner", "start_date", "due_date", "status", "progress", "weight", "dependency_ids", "is_critical", "remarks"]
        editor = prepare_editor_frame(tasks, columns)
        if "task_type" in editor:
            editor["task_type"] = editor["task_type"].fillna(default_task_type)
        if "status" in editor:
            editor["status"] = editor["status"].fillna("Not Started")
        if "progress" in editor:
            editor["progress"] = editor["progress"].fillna(0)
        if "weight" in editor:
            editor["weight"] = editor["weight"].fillna(1.0)
        for col in ["start_date", "due_date"]:
            if col in editor:
                editor[col] = pd.to_datetime(editor[col], errors="coerce").dt.date
        edited = st.data_editor(
            editor,
            use_container_width=True,
            hide_index=True,
            height=420,
            num_rows="dynamic",
            key=f"task_sheet_{project_id}_{editor_key}",
            column_config={
                **editor_common_config(),
                "task_type": st.column_config.SelectboxColumn("Task Type", options=["Major", "Daily"]),
                "status": st.column_config.SelectboxColumn("Status", options=STATUSES),
                "start_date": st.column_config.DateColumn("Start Date"),
                "due_date": st.column_config.DateColumn("Due Date"),
                "progress": st.column_config.NumberColumn("Progress %", min_value=0, max_value=100),
                "weight": st.column_config.NumberColumn("Weight", min_value=0.1),
                "is_critical": st.column_config.CheckboxColumn("Critical"),
            },
        )
        unsaved_rows = edited[
            edited["id"].isna()
            & edited["task_name"].apply(lambda value: bool(clean_text(value)))
        ] if "id" in edited.columns and "task_name" in edited.columns else pd.DataFrame()
        if not unsaved_rows.empty:
            st.warning(f"{len(unsaved_rows)} new task row(s) are not saved yet. Click Save Table before opening Major Tasks.")
        if st.button("Save Table", type="primary", key=f"save_task_sheet_{project_id}_{editor_key}"):
            changed = 0
            skipped = 0
            last_task_type = default_task_type
            last_owner = default_owner
            for _, row in edited.iterrows():
                record_id = row.get("id")
                has_id = not pd.isna(record_id) if record_id is not None else False
                if clean_bool(row.get("_delete")) and has_id:
                    db.delete_record("tasks", int(record_id))
                    changed += 1
                    continue

                current_task_type = clean_text(row.get("task_type")) or last_task_type or default_task_type
                current_owner = clean_text(row.get("owner")) or last_owner or default_owner or "Unassigned"
                if clean_text(row.get("task_type")):
                    last_task_type = clean_text(row.get("task_type"))
                if clean_text(row.get("owner")):
                    last_owner = clean_text(row.get("owner"))
                if not clean_text(row.get("task_name")):
                    continue
                fields = {
                    "task_type": current_task_type,
                    "task_name": clean_text(row.get("task_name")),
                    "owner": current_owner,
                    "start_date": clean_date(row.get("start_date"), date.today()),
                    "due_date": clean_date(row.get("due_date"), date.today() + timedelta(days=7)),
                    "status": clean_text(row.get("status")) or "Not Started",
                    "progress": clean_int(row.get("progress")),
                    "weight": clean_float(row.get("weight"), 1.0),
                    "dependency_ids": clean_text(row.get("dependency_ids")),
                    "is_critical": clean_bool(row.get("is_critical")),
                    "remarks": clean_text(row.get("remarks")),
                }
                if not fields["task_name"]:
                    skipped += 1
                    continue
                if has_id:
                    db.update_record("tasks", int(record_id), fields)
                else:
                    db.insert_record("tasks", project_id, fields)
                changed += 1
            st.success(f"Saved {changed} task change(s).")
            if skipped:
                st.warning(f"Skipped {skipped} row(s) without task names.")
            refresh()


def edit_task_form(tasks: pd.DataFrame) -> None:
    with st.expander("Edit or delete task", expanded=False):
        row = record_selector(tasks, "Task to edit", "task_name")
        if row is None:
            return
        with st.form(f"edit_task_{int(row['id'])}"):
            c1, c2, c3 = st.columns([2, 1, 1])
            task_name = c1.text_input("Task Name", value=str(row["task_name"]))
            task_type = c2.selectbox("Task Type", ["Major", "Daily"], index=select_index(["Major", "Daily"], row["task_type"]))
            status = c3.selectbox("Status", STATUSES, index=select_index(STATUSES, row["status"]))
            c4, c5, c6 = st.columns(3)
            owner = c4.text_input("Owner", value=str(row["owner"]))
            start = c5.date_input("Start Date", value=date_value(row["start_date"], date.today()))
            due = c6.date_input("Due Date", value=date_value(row["due_date"], date.today()))
            c7, c8, c9 = st.columns(3)
            progress = c7.slider("Progress %", 0, 100, int(row["progress"] or 0))
            weight = c8.number_input("Weight", min_value=0.1, value=float(row["weight"] or 1), step=0.1)
            critical = c9.checkbox("Critical Task", value=bool(row["is_critical"]))
            dependencies = st.text_input("Dependency IDs", value=str(row.get("dependency_ids", "") or ""))
            remarks = st.text_area("Remarks", value=str(row.get("remarks", "") or ""))
            c10, c11 = st.columns(2)
            with c10:
                saved = st.form_submit_button("Save Task", type="primary")
            with c11:
                deleted = st.form_submit_button("Delete Task", type="secondary")
        if saved:
            if not task_name or not owner:
                st.error("Task name and owner are required.")
            elif due < start:
                st.error("Due date cannot be before start date.")
            else:
                db.update_record(
                    "tasks",
                    int(row["id"]),
                    {
                        "task_name": task_name,
                        "task_type": task_type,
                        "owner": owner,
                        "start_date": start,
                        "due_date": due,
                        "status": status,
                        "progress": progress,
                        "weight": weight,
                        "dependency_ids": dependencies,
                        "is_critical": critical,
                        "remarks": remarks,
                    },
                )
                st.success("Task updated and project progress recalculated.")
                refresh()
        if deleted:
            db.delete_record("tasks", int(row["id"]))
            st.success("Task deleted and project progress recalculated.")
            refresh()


def edit_milestone_form(milestones: pd.DataFrame) -> None:
    with st.expander("Edit or delete milestone", expanded=False):
        row = record_selector(milestones, "Milestone to edit", "milestone_name")
        if row is None:
            return
        with st.form(f"edit_milestone_{int(row['id'])}"):
            c1, c2, c3 = st.columns(3)
            name = c1.text_input("Milestone Name", value=str(row["milestone_name"]))
            owner = c2.text_input("Owner", value=str(row["owner"] or ""))
            status = c3.selectbox("Status", STATUSES, index=select_index(STATUSES, row["status"]))
            c4, c5, c6 = st.columns(3)
            due = c4.date_input("Due Date", value=date_value(row["due_date"], date.today()))
            baseline = c5.date_input("Baseline Date", value=date_value(row["baseline_date"], due))
            actual = c6.date_input("Actual Date", value=date_value(row["actual_date"], due))
            clear_actual = st.checkbox("Clear actual date", value=pd.isna(row["actual_date"]) or not row["actual_date"])
            c7, c8 = st.columns(2)
            with c7:
                saved = st.form_submit_button("Save Milestone", type="primary")
            with c8:
                deleted = st.form_submit_button("Delete Milestone", type="secondary")
        if saved:
            if not name:
                st.error("Milestone name is required.")
            else:
                db.update_record(
                    "milestones",
                    int(row["id"]),
                    {
                        "milestone_name": name,
                        "owner": owner,
                        "status": status,
                        "due_date": due,
                        "baseline_date": baseline,
                        "actual_date": None if clear_actual else actual,
                    },
                )
                st.success("Milestone updated.")
                refresh()
        if deleted:
            db.delete_record("milestones", int(row["id"]))
            st.success("Milestone deleted.")
            refresh()


def milestone_entry_form(project_id: int) -> None:
    with st.expander("Add milestone", expanded=False):
        with st.form(f"milestone_form_{project_id}"):
            c1, c2, c3 = st.columns(3)
            name = c1.text_input("Milestone Name")
            owner = c2.text_input("Owner")
            status = c3.selectbox("Status", STATUSES)
            due = st.date_input("Due Date", value=date.today() + timedelta(days=14))
            submitted = st.form_submit_button("Add Milestone", type="primary")
        if submitted:
            if not name:
                st.error("Milestone name is required.")
            else:
                db.add_milestone(project_id, name, due, status, owner)
                st.success("Milestone added.")
                refresh()


def budget_entry_form(project_id: int) -> None:
    with st.expander("Add budget item", expanded=False):
        with st.form(f"budget_form_{project_id}"):
            c1, c2, c3 = st.columns(3)
            cost_code = c1.text_input("Cost Code")
            category = c2.text_input("Category")
            owner = c3.text_input("Owner")
            c4, c5, c6, c7 = st.columns(4)
            budget = c4.number_input("Budget", min_value=0.0, value=0.0, step=1000.0)
            actual = c5.number_input("Actual", min_value=0.0, value=0.0, step=1000.0)
            committed = c6.number_input("Committed", min_value=0.0, value=0.0, step=1000.0)
            forecast = c7.number_input("Forecast", min_value=0.0, value=0.0, step=1000.0)
            submitted = st.form_submit_button("Add Budget Item", type="primary")
        if submitted:
            if not cost_code or not category:
                st.error("Cost code and category are required.")
            else:
                db.add_budget_item(project_id, cost_code, category, budget, actual, committed, forecast, owner)
                st.success("Budget item added and project totals recalculated.")
                refresh()


def budget_spreadsheet_editor(project_id: int, budget_frame: pd.DataFrame) -> None:
    with st.expander("Spreadsheet budget editor - paste from Excel", expanded=True):
        columns = ["cost_code", "category", "budget", "actual", "committed", "forecast", "owner"]
        editor = prepare_editor_frame(budget_frame, columns)
        edited = st.data_editor(
            editor,
            use_container_width=True,
            hide_index=True,
            num_rows="dynamic",
            key=f"budget_sheet_{project_id}",
            column_config={
                **editor_common_config(),
                "budget": st.column_config.NumberColumn("Budget", min_value=0),
                "actual": st.column_config.NumberColumn("Actual", min_value=0),
                "committed": st.column_config.NumberColumn("Committed", min_value=0),
                "forecast": st.column_config.NumberColumn("Forecast", min_value=0),
            },
        )
        if st.button("Save Budget Table", type="primary", key=f"save_budget_sheet_{project_id}"):
            changed = 0
            for _, row in edited.iterrows():
                record_id = row.get("id")
                has_id = not pd.isna(record_id) if record_id is not None else False
                if clean_bool(row.get("_delete")) and has_id:
                    db.delete_record("budget_items", int(record_id))
                    changed += 1
                    continue
                if not clean_text(row.get("cost_code")) and not clean_text(row.get("category")):
                    continue
                fields = {
                    "cost_code": clean_text(row.get("cost_code")),
                    "category": clean_text(row.get("category")),
                    "budget": clean_float(row.get("budget")),
                    "actual": clean_float(row.get("actual")),
                    "committed": clean_float(row.get("committed")),
                    "forecast": clean_float(row.get("forecast")),
                    "owner": clean_text(row.get("owner")),
                }
                if not fields["cost_code"] or not fields["category"]:
                    continue
                if has_id:
                    db.update_record("budget_items", int(record_id), fields)
                else:
                    db.insert_record("budget_items", project_id, fields)
                changed += 1
            st.success(f"Saved {changed} budget change(s).")
            refresh()


def edit_budget_form(budget_frame: pd.DataFrame) -> None:
    with st.expander("Edit or delete budget item", expanded=False):
        row = record_selector(budget_frame, "Budget item to edit", "cost_code")
        if row is None:
            return
        with st.form(f"edit_budget_{int(row['id'])}"):
            c1, c2, c3 = st.columns(3)
            cost_code = c1.text_input("Cost Code", value=str(row["cost_code"]))
            category = c2.text_input("Category", value=str(row["category"]))
            owner = c3.text_input("Owner", value=str(row["owner"] or ""))
            c4, c5, c6, c7 = st.columns(4)
            budget = c4.number_input("Budget", min_value=0.0, value=float(row["budget"] or 0), step=1000.0)
            actual = c5.number_input("Actual", min_value=0.0, value=float(row["actual"] or 0), step=1000.0)
            committed = c6.number_input("Committed", min_value=0.0, value=float(row["committed"] or 0), step=1000.0)
            forecast = c7.number_input("Forecast", min_value=0.0, value=float(row["forecast"] or 0), step=1000.0)
            c8, c9 = st.columns(2)
            with c8:
                saved = st.form_submit_button("Save Budget Item", type="primary")
            with c9:
                deleted = st.form_submit_button("Delete Budget Item", type="secondary")
        if saved:
            if not cost_code or not category:
                st.error("Cost code and category are required.")
            else:
                db.update_record(
                    "budget_items",
                    int(row["id"]),
                    {
                        "cost_code": cost_code,
                        "category": category,
                        "budget": budget,
                        "actual": actual,
                        "committed": committed,
                        "forecast": forecast,
                        "owner": owner,
                    },
                )
                st.success("Budget item updated and project totals recalculated.")
                refresh()
        if deleted:
            db.delete_record("budget_items", int(row["id"]))
            st.success("Budget item deleted and project totals recalculated.")
            refresh()


def risk_entry_form(project_id: int) -> None:
    with st.expander("Add risk", expanded=False):
        with st.form(f"risk_form_{project_id}"):
            c1, c2, c3 = st.columns(3)
            title = c1.text_input("Risk Title")
            category = c2.selectbox("Category", ["Project", "Authority", "Vendor", "Construction", "Safety", "Documentation"])
            severity = c3.selectbox("Severity", ["Low", "Medium", "High", "Critical"])
            c4, c5, c6 = st.columns(3)
            probability = c4.selectbox("Probability", ["Low", "Medium", "High"])
            owner = c5.text_input("Owner")
            due_date = c6.date_input("Review Date", value=date.today() + timedelta(days=7))
            status = st.selectbox("Status", ["Open", "Monitoring", "Closed"])
            mitigation = st.text_area("Mitigation / Catch-up Plan")
            submitted = st.form_submit_button("Add Risk", type="primary")
        if submitted:
            if not title or not owner or not mitigation:
                st.error("Title, owner, and mitigation plan are required.")
            else:
                db.add_risk(project_id, title, severity, owner, status, mitigation, category, probability, due_date)
                st.success("Risk added.")
                refresh()


def risk_spreadsheet_editor(project_id: int, risks: pd.DataFrame) -> None:
    with st.expander("Spreadsheet risk editor - paste from Excel", expanded=True):
        columns = ["title", "category", "severity", "probability", "owner", "status", "due_date", "mitigation_plan"]
        editor = prepare_editor_frame(risks, columns)
        if "due_date" in editor:
            editor["due_date"] = pd.to_datetime(editor["due_date"], errors="coerce").dt.date
        severity_options = ["Low", "Medium", "High", "Critical"]
        probability_options = ["Low", "Medium", "High"]
        status_options = ["Open", "Monitoring", "Closed"]
        edited = st.data_editor(
            editor,
            use_container_width=True,
            hide_index=True,
            num_rows="dynamic",
            key=f"risk_sheet_{project_id}",
            column_config={
                **editor_common_config(),
                "severity": st.column_config.SelectboxColumn("Severity", options=severity_options),
                "probability": st.column_config.SelectboxColumn("Probability", options=probability_options),
                "status": st.column_config.SelectboxColumn("Status", options=status_options),
                "due_date": st.column_config.DateColumn("Review Date"),
            },
        )
        if st.button("Save Risk Table", type="primary", key=f"save_risk_sheet_{project_id}"):
            changed = 0
            for _, row in edited.iterrows():
                record_id = row.get("id")
                has_id = not pd.isna(record_id) if record_id is not None else False
                if clean_bool(row.get("_delete")) and has_id:
                    db.delete_record("risk_logs", int(record_id))
                    changed += 1
                    continue
                if not clean_text(row.get("title")) and not clean_text(row.get("owner")):
                    continue
                fields = {
                    "title": clean_text(row.get("title")),
                    "category": clean_text(row.get("category")) or "Project",
                    "severity": clean_text(row.get("severity")) or "Medium",
                    "probability": clean_text(row.get("probability")) or "Medium",
                    "owner": clean_text(row.get("owner")),
                    "status": clean_text(row.get("status")) or "Open",
                    "due_date": clean_date(row.get("due_date")),
                    "mitigation_plan": clean_text(row.get("mitigation_plan")) or "-",
                }
                if not fields["title"] or not fields["owner"]:
                    continue
                if has_id:
                    db.update_record("risk_logs", int(record_id), fields)
                else:
                    db.insert_record("risk_logs", project_id, fields)
                changed += 1
            st.success(f"Saved {changed} risk change(s).")
            refresh()


def edit_risk_form(risks: pd.DataFrame) -> None:
    with st.expander("Edit or delete risk", expanded=False):
        row = record_selector(risks, "Risk to edit", "title")
        if row is None:
            return
        severity_options = ["Low", "Medium", "High", "Critical"]
        probability_options = ["Low", "Medium", "High"]
        status_options = ["Open", "Monitoring", "Closed"]
        with st.form(f"edit_risk_{int(row['id'])}"):
            c1, c2, c3 = st.columns(3)
            title = c1.text_input("Risk Title", value=str(row["title"]))
            category = c2.text_input("Category", value=str(row["category"] or "Project"))
            severity = c3.selectbox("Severity", severity_options, index=select_index(severity_options, row["severity"]))
            c4, c5, c6 = st.columns(3)
            probability = c4.selectbox("Probability", probability_options, index=select_index(probability_options, row["probability"]))
            owner = c5.text_input("Owner", value=str(row["owner"]))
            due_date = c6.date_input("Review Date", value=date_value(row["due_date"], date.today()))
            status = st.selectbox("Status", status_options, index=select_index(status_options, row["status"]))
            mitigation = st.text_area("Mitigation / Catch-up Plan", value=str(row["mitigation_plan"]))
            c7, c8 = st.columns(2)
            with c7:
                saved = st.form_submit_button("Save Risk", type="primary")
            with c8:
                deleted = st.form_submit_button("Delete Risk", type="secondary")
        if saved:
            if not title or not owner or not mitigation:
                st.error("Title, owner, and mitigation plan are required.")
            else:
                db.update_record(
                    "risk_logs",
                    int(row["id"]),
                    {
                        "title": title,
                        "category": category,
                        "severity": severity,
                        "probability": probability,
                        "owner": owner,
                        "status": status,
                        "mitigation_plan": mitigation,
                        "due_date": due_date,
                    },
                )
                st.success("Risk updated.")
                refresh()
        if deleted:
            db.delete_record("risk_logs", int(row["id"]))
            st.success("Risk deleted.")
            refresh()


def issue_entry_form(project_id: int) -> None:
    with st.expander("Add issue", expanded=False):
        with st.form(f"issue_form_{project_id}"):
            c1, c2, c3 = st.columns(3)
            title = c1.text_input("Issue Title")
            severity = c2.selectbox("Severity", ["Low", "Medium", "High", "Critical"])
            owner = c3.text_input("Owner")
            c4, c5 = st.columns(2)
            status = c4.selectbox("Status", ["Open", "In Progress", "Closed"])
            due_date = c5.date_input("Resolution Due", value=date.today() + timedelta(days=7))
            plan = st.text_area("Resolution Plan")
            submitted = st.form_submit_button("Add Issue", type="primary")
        if submitted:
            if not title or not owner or not plan:
                st.error("Title, owner, and resolution plan are required.")
            else:
                db.add_issue(project_id, title, severity, owner, status, plan, due_date)
                st.success("Issue added.")
                refresh()


def issue_spreadsheet_editor(project_id: int, issues: pd.DataFrame) -> None:
    with st.expander("Spreadsheet issue editor - paste from Excel", expanded=True):
        columns = ["title", "severity", "owner", "status", "due_date", "resolution_plan"]
        editor = prepare_editor_frame(issues, columns)
        if "due_date" in editor:
            editor["due_date"] = pd.to_datetime(editor["due_date"], errors="coerce").dt.date
        severity_options = ["Low", "Medium", "High", "Critical"]
        status_options = ["Open", "In Progress", "Closed"]
        edited = st.data_editor(
            editor,
            use_container_width=True,
            hide_index=True,
            num_rows="dynamic",
            key=f"issue_sheet_{project_id}",
            column_config={
                **editor_common_config(),
                "severity": st.column_config.SelectboxColumn("Severity", options=severity_options),
                "status": st.column_config.SelectboxColumn("Status", options=status_options),
                "due_date": st.column_config.DateColumn("Resolution Due"),
            },
        )
        if st.button("Save Issue Table", type="primary", key=f"save_issue_sheet_{project_id}"):
            changed = 0
            for _, row in edited.iterrows():
                record_id = row.get("id")
                has_id = not pd.isna(record_id) if record_id is not None else False
                if clean_bool(row.get("_delete")) and has_id:
                    db.delete_record("issues", int(record_id))
                    changed += 1
                    continue
                if not clean_text(row.get("title")) and not clean_text(row.get("owner")):
                    continue
                fields = {
                    "title": clean_text(row.get("title")),
                    "severity": clean_text(row.get("severity")) or "Medium",
                    "owner": clean_text(row.get("owner")),
                    "status": clean_text(row.get("status")) or "Open",
                    "due_date": clean_date(row.get("due_date")),
                    "resolution_plan": clean_text(row.get("resolution_plan")) or "-",
                }
                if not fields["title"] or not fields["owner"]:
                    continue
                if has_id:
                    db.update_record("issues", int(record_id), fields)
                else:
                    db.insert_record("issues", project_id, fields)
                changed += 1
            st.success(f"Saved {changed} issue change(s).")
            refresh()


def edit_issue_form(issues: pd.DataFrame) -> None:
    with st.expander("Edit or delete issue", expanded=False):
        row = record_selector(issues, "Issue to edit", "title")
        if row is None:
            return
        severity_options = ["Low", "Medium", "High", "Critical"]
        status_options = ["Open", "In Progress", "Closed"]
        with st.form(f"edit_issue_{int(row['id'])}"):
            c1, c2, c3 = st.columns(3)
            title = c1.text_input("Issue Title", value=str(row["title"]))
            severity = c2.selectbox("Severity", severity_options, index=select_index(severity_options, row["severity"]))
            owner = c3.text_input("Owner", value=str(row["owner"]))
            c4, c5 = st.columns(2)
            status = c4.selectbox("Status", status_options, index=select_index(status_options, row["status"]))
            due_date = c5.date_input("Resolution Due", value=date_value(row["due_date"], date.today()))
            plan = st.text_area("Resolution Plan", value=str(row["resolution_plan"]))
            c6, c7 = st.columns(2)
            with c6:
                saved = st.form_submit_button("Save Issue", type="primary")
            with c7:
                deleted = st.form_submit_button("Delete Issue", type="secondary")
        if saved:
            if not title or not owner or not plan:
                st.error("Title, owner, and resolution plan are required.")
            else:
                db.update_record(
                    "issues",
                    int(row["id"]),
                    {
                        "title": title,
                        "severity": severity,
                        "owner": owner,
                        "status": status,
                        "resolution_plan": plan,
                        "due_date": due_date,
                    },
                )
                st.success("Issue updated.")
                refresh()
        if deleted:
            db.delete_record("issues", int(row["id"]))
            st.success("Issue deleted.")
            refresh()


def team_entry_form(project_id: int) -> None:
    with st.expander("Add team member", expanded=False):
        with st.form(f"team_form_{project_id}"):
            c1, c2, c3 = st.columns(3)
            name = c1.text_input("Name")
            role = c2.text_input("Project Role")
            user_role = c3.selectbox("User Role", USER_ROLES)
            c4, c5 = st.columns(2)
            email = c4.text_input("Email")
            phone = c5.text_input("Phone")
            c6, c7 = st.columns(2)
            capacity = c6.number_input("Capacity Hours", min_value=0.0, value=40.0, step=1.0)
            allocated = c7.number_input("Allocated Hours", min_value=0.0, value=32.0, step=1.0)
            submitted = st.form_submit_button("Add Team Member", type="primary")
        if submitted:
            if not name or not role:
                st.error("Name and project role are required.")
            else:
                db.add_team_member(project_id, name, role, email, phone, user_role, capacity, allocated)
                st.success("Team member added.")
                refresh()


def edit_team_form(team: pd.DataFrame) -> None:
    with st.expander("Edit or delete team member", expanded=False):
        row = record_selector(team, "Team member to edit", "name")
        if row is None:
            return
        with st.form(f"edit_team_{int(row['id'])}"):
            c1, c2, c3 = st.columns(3)
            name = c1.text_input("Name", value=str(row["name"]))
            role = c2.text_input("Project Role", value=str(row["role"]))
            user_role = c3.selectbox("User Role", USER_ROLES, index=select_index(USER_ROLES, row["user_role"]))
            c4, c5 = st.columns(2)
            email = c4.text_input("Email", value=str(row["email"] or ""))
            phone = c5.text_input("Phone", value=str(row["phone"] or ""))
            c6, c7 = st.columns(2)
            capacity = c6.number_input("Capacity Hours", min_value=0.0, value=float(row["capacity_hours"] or 0), step=1.0)
            allocated = c7.number_input("Allocated Hours", min_value=0.0, value=float(row["allocated_hours"] or 0), step=1.0)
            c8, c9 = st.columns(2)
            with c8:
                saved = st.form_submit_button("Save Team Member", type="primary")
            with c9:
                deleted = st.form_submit_button("Delete Team Member", type="secondary")
        if saved:
            if not name or not role:
                st.error("Name and project role are required.")
            else:
                db.update_record(
                    "team_members",
                    int(row["id"]),
                    {
                        "name": name,
                        "role": role,
                        "user_role": user_role,
                        "email": email,
                        "phone": phone,
                        "capacity_hours": capacity,
                        "allocated_hours": allocated,
                    },
                )
                st.success("Team member updated.")
                refresh()
        if deleted:
            db.delete_record("team_members", int(row["id"]))
            st.success("Team member deleted.")
            refresh()


def solar_pv_module(data: dict[str, pd.DataFrame]) -> None:
    st.title("Solar PV Control Module")
    st.caption("Authority, SP, LEW, QP, engineering, construction, and commissioning tracker.")
    authority = data["authority"]
    solar_projects = data["projects"][data["projects"]["portfolio"].str.contains("Solar", case=False, na=False)]
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        metric_card("Solar Projects", str(len(solar_projects)), "PV portfolio")
    with c2:
        metric_card("Open Submissions", str(len(authority[~authority["status"].isin(["Done", "Closed"])])), "Authority actions")
    with c3:
        metric_card("At Risk", str(len(authority[authority["status"].isin(["At Risk", "Delayed"])])), "Escalation queue")
    with c4:
        metric_card("Authorities", str(authority["authority"].nunique() if not authority.empty else 0), "JTC/BCA/SCDF/EMA/SP/LEW/QP")
    if not authority.empty:
        status_mix = authority.groupby(["authority", "status"], as_index=False).size()
        fig = px.bar(status_mix, x="authority", y="size", color="status", color_discrete_map=STATUS_COLORS, title="Submission Tracker by Authority")
        fig.update_layout(yaxis_title="Packages", xaxis_title="")
        st.plotly_chart(fig, use_container_width=True)

    with st.expander("Add authority or tracker item", expanded=False):
        project_id, _ = project_selector(data, "Project")
        if project_id:
            with st.form("authority_form"):
                c1, c2, c3 = st.columns(3)
                authority_name = c1.selectbox("Tracker", AUTHORITY_TYPES)
                package = c2.text_input("Package / Workstream")
                owner = c3.text_input("Owner")
                c4, c5, c6 = st.columns(3)
                target = c4.date_input("Target Date", value=date.today() + timedelta(days=14))
                status = c5.selectbox("Status", STATUSES)
                reference = c6.text_input("Reference No.")
                remarks = st.text_area("Remarks")
                submitted = st.form_submit_button("Add Tracker Item", type="primary")
            if submitted:
                if not package or not owner:
                    st.error("Package and owner are required.")
                else:
                    db.add_authority_submission(project_id, authority_name, package, owner, target, status, reference, remarks)
                    st.success("Tracker item added.")
                    refresh()
    edit_authority_form(authority)
    show_table(authority, ["project_name", "authority", "package_name", "owner", "target_date", "submitted_date", "approval_date", "status", "reference_no", "remarks"], 430)


def edit_authority_form(authority: pd.DataFrame) -> None:
    with st.expander("Edit or delete Solar PV tracker item", expanded=False):
        row = record_selector(authority, "Tracker item to edit", "package_name")
        if row is None:
            return
        with st.form(f"edit_authority_{int(row['id'])}"):
            c1, c2, c3 = st.columns(3)
            authority_name = c1.selectbox("Tracker", AUTHORITY_TYPES, index=select_index(AUTHORITY_TYPES, row["authority"]))
            package = c2.text_input("Package / Workstream", value=str(row["package_name"]))
            owner = c3.text_input("Owner", value=str(row["owner"]))
            c4, c5, c6 = st.columns(3)
            target = c4.date_input("Target Date", value=date_value(row["target_date"], date.today()))
            status = c5.selectbox("Status", STATUSES, index=select_index(STATUSES, row["status"]))
            reference = c6.text_input("Reference No.", value=str(row["reference_no"] or ""))
            c7, c8 = st.columns(2)
            submitted_date = c7.date_input("Submitted Date", value=date_value(row["submitted_date"], target))
            approval_date = c8.date_input("Approval Date", value=date_value(row["approval_date"], target))
            clear_submitted = st.checkbox("Clear submitted date", value=pd.isna(row["submitted_date"]) or not row["submitted_date"])
            clear_approval = st.checkbox("Clear approval date", value=pd.isna(row["approval_date"]) or not row["approval_date"])
            remarks = st.text_area("Remarks", value=str(row["remarks"] or ""))
            c9, c10 = st.columns(2)
            with c9:
                saved = st.form_submit_button("Save Tracker Item", type="primary")
            with c10:
                deleted = st.form_submit_button("Delete Tracker Item", type="secondary")
        if saved:
            if not package or not owner:
                st.error("Package and owner are required.")
            else:
                db.update_record(
                    "authority_submissions",
                    int(row["id"]),
                    {
                        "authority": authority_name,
                        "package_name": package,
                        "owner": owner,
                        "target_date": target,
                        "submitted_date": None if clear_submitted else submitted_date,
                        "approval_date": None if clear_approval else approval_date,
                        "status": status,
                        "reference_no": reference,
                        "remarks": remarks,
                    },
                )
                st.success("Tracker item updated.")
                refresh()
        if deleted:
            db.delete_record("authority_submissions", int(row["id"]))
            st.success("Tracker item deleted.")
            refresh()


def reports_center(data: dict[str, pd.DataFrame]) -> None:
    st.title("Reports")
    report_type = st.selectbox("Report Type", REPORT_TYPES)
    projects, tasks, risks, budget, team = data["projects"], data["tasks"], data["risks"], data["budget"], data["team"]
    st.markdown(f"### {report_type}")
    summary = {
        "Projects": len(projects),
        "Active": len(projects[projects["status"].isin(["In Progress", "At Risk", "Delayed"])]),
        "At Risk / Delayed": len(projects[projects["status"].isin(["At Risk", "Delayed"])]),
        "Portfolio Progress": f"{round(projects['progress'].mean()) if not projects.empty else 0}%",
        "Budget": money(projects["budget"].sum()),
        "Actual": money(projects["actual_cost"].sum()),
        "Open Risks": len(risks[risks["status"].str.lower() != "closed"]) if not risks.empty else 0,
        "Resource Utilization": f"{round(team['allocated_hours'].sum() / team['capacity_hours'].sum() * 100) if not team.empty and team['capacity_hours'].sum() else 0}%",
    }
    cols = st.columns(4)
    for i, (label, value) in enumerate(summary.items()):
        with cols[i % 4]:
            st.metric(label, value)
    st.markdown("#### Executive Narrative")
    st.write(build_report_narrative(report_type, projects, tasks, risks, budget))
    tabs = st.tabs(["Progress", "Cost", "Resource", "Risk", "Export Tables"])
    with tabs[0]:
        fig = px.bar(projects, x="project_name", y="progress", color="status", color_discrete_map=STATUS_COLORS, title="Progress Report")
        st.plotly_chart(fig, use_container_width=True)
    with tabs[1]:
        if not budget.empty:
            cost = budget.groupby("project_name", as_index=False)[["budget", "actual", "forecast"]].sum()
            fig = px.bar(cost.melt("project_name", var_name="type", value_name="amount"), x="project_name", y="amount", color="type", barmode="group", title="Cost Report")
            st.plotly_chart(fig, use_container_width=True)
    with tabs[2]:
        show_table(team.assign(utilization=(team["allocated_hours"] / team["capacity_hours"] * 100).round(0)), ["project_name", "name", "role", "user_role", "capacity_hours", "allocated_hours", "utilization"], 330)
    with tabs[3]:
        show_table(risks, ["project_name", "title", "category", "severity", "probability", "owner", "status", "mitigation_plan"], 330)
    with tabs[4]:
        st.download_button("Download Project Register CSV", projects.to_csv(index=False), "project_register.csv", "text/csv")
        st.download_button("Download Task Register CSV", tasks.to_csv(index=False), "task_register.csv", "text/csv")


def build_report_narrative(report_type: str, projects: pd.DataFrame, tasks: pd.DataFrame, risks: pd.DataFrame, budget: pd.DataFrame) -> str:
    active = len(projects[projects["status"].isin(["In Progress", "At Risk", "Delayed"])])
    attention = len(projects[projects["status"].isin(["At Risk", "Delayed"])])
    overdue = 0
    if not tasks.empty:
        overdue = len(tasks[(pd.to_datetime(tasks["due_date"]) < pd.Timestamp(date.today())) & (~tasks["status"].isin(["Done", "Closed"]))])
    actual = float(projects["actual_cost"].sum()) if not projects.empty else 0
    total_budget = float(projects["budget"].sum()) if not projects.empty else 0
    return (
        f"{report_type} generated on {date.today().isoformat()}. The portfolio has {active} active projects, "
        f"with {attention} requiring management attention and {overdue} overdue open tasks. "
        f"Budget performance is {money(actual)} actual against {money(total_budget)} approved budget. "
        "Priority actions are to close delayed authority submissions, protect critical-path activities, and rebalance overloaded resources."
    )


def show_upload_section(project_id: int, documents: pd.DataFrame) -> None:
    with st.form("document_upload_form"):
        c1, c2 = st.columns(2)
        folder = c1.selectbox("Folder", ["General", "Contracts", "Drawings", "Authority", "Meetings", "Handover"])
        version = c2.text_input("Version", value="v1")
        uploaded_by = st.text_input("Uploaded By", value="Project Admin")
        files = st.file_uploader("Upload Project Documents", accept_multiple_files=True)
        submitted = st.form_submit_button("Save Documents", type="primary")
    if submitted:
        if not files:
            st.error("Select at least one document.")
        else:
            project_dir = db.UPLOAD_DIR / f"project_{project_id}" / folder
            project_dir.mkdir(parents=True, exist_ok=True)
            for file in files:
                target = project_dir / f"{Path(file.name).stem}_{version}{Path(file.name).suffix}"
                target.write_bytes(file.getbuffer())
                db.log_document(project_id, file.name, str(target), uploaded_by, folder, version)
            st.success(f"Uploaded {len(files)} document(s).")
            refresh()
    show_table(documents, ["folder", "file_name", "version", "uploaded_by", "uploaded_at", "file_path"], 320)


def documents_center(data: dict[str, pd.DataFrame]) -> None:
    st.title("Document Management")
    project_id, _ = project_selector(data, "Project")
    if project_id is None:
        return
    docs = data["documents"][data["documents"]["project_id"] == project_id]
    show_upload_section(project_id, docs)


def notification_candidates(tasks: pd.DataFrame, milestones: pd.DataFrame) -> pd.DataFrame:
    today = pd.Timestamp(date.today())
    task_dates = tasks.copy()
    if task_dates.empty:
        return task_dates
    task_dates["due_date_dt"] = pd.to_datetime(task_dates["due_date"])
    return task_dates[
        ((task_dates["due_date_dt"] <= today + pd.Timedelta(days=7)) & (~task_dates["status"].isin(["Done", "Closed"])))
        | (task_dates["status"].isin(["At Risk", "Delayed"]))
    ].sort_values(["due_date_dt", "status"])


def send_email(settings: dict, subject: str, body: str, password: str) -> tuple[bool, str]:
    msg = EmailMessage()
    msg["From"] = settings["sender_email"]
    msg["To"] = settings["receiver_email"]
    msg["Subject"] = subject
    msg.set_content(body)
    try:
        with smtplib.SMTP(settings["smtp_server"], int(settings["smtp_port"]), timeout=30) as server:
            if int(settings.get("use_tls", 1)):
                server.starttls()
            if password:
                server.login(settings["sender_email"], password)
            server.send_message(msg)
        return True, ""
    except Exception as exc:
        return False, str(exc)


def notifications_center(data: dict[str, pd.DataFrame]) -> None:
    st.title("Notifications")
    st.caption("Email notifications, due date reminders, overdue alerts, and milestone alerts.")
    settings_df = db.get_email_settings()
    current = settings_df.iloc[0].to_dict() if not settings_df.empty else {}
    with st.form("email_settings_form"):
        c1, c2 = st.columns(2)
        sender = c1.text_input("Sender Email", value=current.get("sender_email", ""))
        receiver = c2.text_input("Receiver Email", value=current.get("receiver_email", ""))
        c3, c4, c5 = st.columns([2, 1, 1])
        smtp_server = c3.text_input("SMTP Server", value=current.get("smtp_server", "smtp.gmail.com"))
        smtp_port = c4.number_input("SMTP Port", value=int(current.get("smtp_port", 587)), min_value=1, max_value=65535)
        use_tls = c5.checkbox("Use TLS", value=bool(current.get("use_tls", 1)))
        saved = st.form_submit_button("Save SMTP Settings", type="primary")
    if saved:
        if not sender or not receiver or not smtp_server:
            st.error("Sender email, receiver email, and SMTP server are required.")
        else:
            db.save_email_settings(sender, receiver, smtp_server, int(smtp_port), use_tls)
            st.success("SMTP settings saved.")
            refresh()

    candidates = notification_candidates(data["tasks"], data["milestones"])
    show_table(candidates, ["project_name", "task_type", "task_name", "owner", "due_date", "status", "progress", "remarks"], 300)
    subject = st.text_input("Email Subject", value="Project alert: due soon, overdue, and at-risk work")
    body = st.text_area("Email Body", value=build_notification_body(candidates), height=260)
    password = st.text_input("SMTP Password / App Password", type="password")
    if st.button("Send Email Notification", type="primary", disabled=candidates.empty):
        settings_df = db.get_email_settings()
        if settings_df.empty:
            st.error("Save SMTP settings before sending.")
        else:
            settings = settings_df.iloc[0].to_dict()
            ok, error = send_email(settings, subject, body, password)
            task_id = int(candidates.iloc[0]["id"]) if not candidates.empty else None
            db.log_email_notification(task_id, settings["receiver_email"], subject, body, "Sent" if ok else "Failed", error)
            st.success("Email notification sent.") if ok else st.error(f"Email failed: {error}")
            refresh()
    st.markdown('<div class="small-title">Notification History</div>', unsafe_allow_html=True)
    show_table(data["notifications"], ["receiver_email", "subject", "status", "error_message", "sent_at"], 260)


def build_notification_body(tasks: pd.DataFrame) -> str:
    if tasks.empty:
        return "No task notifications are required today."
    lines = ["Dear Project Team,", "", "Please review the following project items requiring attention:", ""]
    today = pd.Timestamp(date.today())
    for row in tasks.itertuples():
        due = pd.Timestamp(row.due_date)
        category = "At Risk" if row.status == "At Risk" else "Delayed" if row.status == "Delayed" else "Overdue" if due < today else "Due Soon"
        lines.extend(
            [
                f"- {category}: {row.project_name} | {row.task_name}",
                f"  Owner: {row.owner}",
                f"  Due Date: {row.due_date}",
                f"  Status: {row.status} | Progress: {row.progress}%",
                f"  Remarks: {row.remarks or '-'}",
                "",
            ]
        )
    lines.extend(["Regards,", "Project Management System"])
    return "\n".join(lines)


def database_admin(data: dict[str, pd.DataFrame]) -> None:
    st.title("Database & Admin")
    if db.using_postgres():
        st.caption("Database: PostgreSQL permanent cloud database")
        st.success("Permanent saving is enabled. Project, task, major task, schedule, budget, risk, issue, and team changes are saved to PostgreSQL.")
    else:
        st.caption(f"SQLite database: {db.DB_PATH}")
        st.warning(
            "This app currently saves edits to a local SQLite file. On Streamlit Cloud, "
            "that file can be reset when the app restarts, redeploys, or the cloud container "
            "is recreated. For permanent cloud saving, add DATABASE_URL in Streamlit Secrets."
        )
    if not db.using_postgres() and db.DB_PATH.exists():
        st.download_button(
            "Download SQLite Backup",
            db.DB_PATH.read_bytes(),
            file_name="project_management_backup.db",
            mime="application/octet-stream",
        )
    selected = st.selectbox("Table", list(data.keys()))
    show_table(data[selected], height=520)
    if st.button("Reload Database"):
        refresh()


def main() -> None:
    with st.sidebar:
        st.title("ProjectOS")
        st.caption("Enterprise project management")
        theme = st.radio("Theme", ["Light", "Dark"], horizontal=True)
        role = st.selectbox("Role", USER_ROLES, index=2)
        st.markdown("---")

    apply_styles(theme)

    try:
        db.init_db(seed=True)
        data = load_data()
    except Exception as exc:
        st.error("The app started, but the project database could not be initialized.")
        st.exception(exc)
        st.stop()

    with st.sidebar:
        portfolios = st.multiselect("Portfolio", sorted(data["projects"]["portfolio"].dropna().unique().tolist()))
        statuses = st.multiselect("Status", STATUSES)
        st.markdown("---")
        page = st.radio(
            "Navigation",
            [
                "Main Dashboard",
                "Project Management",
                "Project Workspace",
                "Solar PV Module",
                "Reports",
                "Documents",
                "Notifications",
                "Database",
            ],
        )
        st.caption(f"Signed in as {role}")

    filtered = filter_data(data, portfolios, statuses)
    if page == "Main Dashboard":
        portfolio_overview(filtered)
    elif page == "Project Management":
        project_setup(filtered)
    elif page == "Project Workspace":
        project_workspace(filtered)
    elif page == "Solar PV Module":
        solar_pv_module(filtered)
    elif page == "Reports":
        reports_center(filtered)
    elif page == "Documents":
        documents_center(filtered)
    elif page == "Notifications":
        notifications_center(filtered)
    elif page == "Database":
        database_admin(filtered)


if __name__ == "__main__":
    main()
