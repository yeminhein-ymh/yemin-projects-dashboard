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
        if not milestones.empty:
            show_table(milestones, ["milestone_name", "owner", "due_date", "baseline_date", "actual_date", "status"], 260)
    with tabs[1]:
        show_gantt(schedules, tasks)
    with tabs[2]:
        task_entry_form(project_id)
        show_table(tasks, ["task_type", "task_name", "owner", "start_date", "due_date", "status", "progress", "weight", "dependency_ids", "is_critical", "remarks"], 380)
    with tabs[3]:
        majors = tasks[tasks["task_type"].eq("Major")]
        fig = px.bar(majors, x="task_name", y="progress", color="status", color_discrete_map=STATUS_COLORS, title="Major Task Weighted Progress") if not majors.empty else None
        if fig:
            fig.update_layout(xaxis_title="", yaxis_title="Progress %", yaxis_range=[0, 100])
            st.plotly_chart(fig, use_container_width=True)
        show_table(majors, ["task_name", "owner", "due_date", "status", "progress", "weight", "dependency_ids", "remarks"], 330)
    with tabs[4]:
        risk_entry_form(project_id)
        show_table(risks, ["title", "category", "severity", "probability", "owner", "status", "due_date", "mitigation_plan"], 360)
    with tabs[5]:
        issue_entry_form(project_id)
        show_table(issues, ["title", "severity", "owner", "status", "due_date", "resolution_plan"], 360)
    with tabs[6]:
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
        show_table(budget, ["cost_code", "category", "budget", "actual", "committed", "forecast", "owner"], 330)
    with tabs[7]:
        show_upload_section(project_id, docs)
    with tabs[8]:
        show_table(meetings, ["meeting_date", "title", "attendees", "decisions", "actions"], 350)
    with tabs[9]:
        show_table(team, ["name", "role", "user_role", "email", "phone", "capacity_hours", "allocated_hours"], 350)


def show_gantt(schedules: pd.DataFrame, tasks: pd.DataFrame) -> None:
    if schedules.empty and tasks.empty:
        st.info("No schedule or task records yet.")
        return
    source = schedules.rename(columns={"activity_name": "name", "planned_start": "start", "planned_finish": "finish"}).copy()
    source["record_type"] = "Schedule"
    task_source = tasks.rename(columns={"task_name": "name", "start_date": "start", "due_date": "finish"}).copy()
    task_source["record_type"] = task_source["task_type"]
    gantt = pd.concat([source[["name", "start", "finish", "status", "progress", "record_type"]], task_source[["name", "start", "finish", "status", "progress", "record_type"]]], ignore_index=True)
    fig = px.timeline(gantt, x_start="start", x_end="finish", y="name", color="status", color_discrete_map=STATUS_COLORS, hover_data=["progress", "record_type"], title="Baseline / Actual Schedule Gantt")
    fig.update_yaxes(autorange="reversed")
    fig.update_layout(margin=dict(t=45, l=10, r=10, b=10), yaxis_title="")
    st.plotly_chart(fig, use_container_width=True)
    show_table(schedules, ["activity_name", "planned_start", "planned_finish", "baseline_start", "baseline_finish", "actual_start", "actual_finish", "delay_days", "progress", "status", "remarks"], 300)


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
            db.add_schedule(project_id, "Overall baseline schedule", start, target, None, None, progress, status, "Created from project template.")
            db.add_milestone(project_id, "Project completion", target, status, manager)
            st.success(f"Created project: {project_name}")
            refresh()
    st.markdown('<div class="small-title">Project Register</div>', unsafe_allow_html=True)
    show_table(data["projects"], ["project_name", "client_name", "portfolio", "template_name", "project_manager", "priority", "status", "progress", "budget", "actual_cost"], 360)


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
    show_table(authority, ["project_name", "authority", "package_name", "owner", "target_date", "submitted_date", "approval_date", "status", "reference_no", "remarks"], 430)


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
    st.caption(f"SQLite database: {db.DB_PATH}")
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
