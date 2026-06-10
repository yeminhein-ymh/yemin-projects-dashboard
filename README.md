# Enterprise Project Management Dashboard

A professional Streamlit-based project management system for engineering, construction, and Solar PV delivery teams. The app combines a Notion-style workspace, Monday.com-style registers, and Microsoft Project-style schedule controls in one SQLite-backed web dashboard.

## Features

- Portfolio command center with total projects, active projects, at-risk projects, delayed projects, weighted progress, budget vs actual, upcoming milestones, critical tasks, and resource utilization.
- Project management workspace with unlimited projects, templates, major tasks, daily tasks, dependencies, milestones, weighted progress, baseline dates, actual dates, and Gantt charts.
- Project folder tabs for overview, schedule, tasks, major tasks, risks, issues, budget, documents, meetings, and team.
- Solar PV module for JTC, BCA, SCDF, EMA, SP, LEW, QP, engineering, construction, and commissioning tracking.
- Reports center for weekly, monthly, executive, progress, cost, and resource reporting with CSV exports.
- Document management with uploads, folder structure, and version metadata.
- SMTP notification center for due date reminders, overdue alerts, milestone-style alerts, and at-risk/delayed task alerts.
- Role selector for Admin, Project Director, Project Manager, Engineer, Contractor, and Client Viewer.
- Modern corporate UI with light/dark modes, Plotly charts, and optional AgGrid tables.

## Technology

- Python
- Streamlit
- SQLite by default, with schema patterns that can be ported to PostgreSQL
- Pandas
- Plotly
- Streamlit AgGrid

## Run Locally

```powershell
cd "C:\Users\Ye Min Hein\OneDrive - Ngee Ann Polytechnic\Documents\Project Management App"
pip install -r requirements.txt
streamlit run app.py
```

For Streamlit Community Cloud, use either `app.py` or `streamlit_app.py` as the entrypoint.

## Data

The database is created at `data/project_management.db` on first run. Existing databases are migrated in place to add the enterprise modules and expanded status model.

The app seeds realistic sample data for fresh databases. For older local databases, it preserves existing projects and adds non-destructive starter records for budgets, milestones, authority trackers, meetings, and issues where needed.

## Folders

```text
Project Management App/
├── app.py
├── streamlit_app.py
├── database.py
├── schema.sql
├── requirements.txt
├── data/
│   └── project_management.db
├── docs/
│   └── database_schema.md
└── uploads/
    └── project_<id>/
```

## Email Setup

Open **Notifications** in the sidebar and configure sender email, receiver email, SMTP server, port, TLS, and an app password when sending. Gmail typically uses `smtp.gmail.com`, port `587`, and TLS enabled.
