# Database Schema

The app uses SQLite at `data/project_management.db`. Tables are created from `schema.sql`, and older local databases are migrated in place on startup.

## Core Tables

- `projects`: project header, portfolio, template, client, managers, baseline/actual dates, status, progress, budget, actual cost, forecast cost, and health score.
- `tasks`: major and daily tasks with owners, dates, baseline dates, actual completion, status, progress, weights, dependencies, and critical-task flag.
- `schedules`: planned, baseline, and actual schedule activities for Gantt views and delay tracking.
- `milestones`: project milestone register with baseline and actual dates.
- `team_members`: project team, role, user role, contact details, capacity hours, and allocated hours.

## Control Tables

- `risk_logs`: project risk register with category, severity, probability, owner, mitigation plan, and review date.
- `issues`: issue register with severity, owner, status, resolution plan, and due date.
- `budget_items`: budget, actual, committed, and forecast values by cost code and category.
- `authority_submissions`: Solar PV and authority trackers for JTC, BCA, SCDF, EMA, SP, LEW, QP, engineering, construction, and commissioning items.

## Collaboration Tables

- `documents`: document metadata with project folder, version, uploader, upload time, and local file path.
- `meetings`: meeting title, attendees, decisions, and actions.
- `email_settings`: active SMTP configuration.
- `email_notifications`: sent/failed notification history.

Foreign keys are enabled by the application connection. Child records cascade when a project is deleted, except task notification history, which keeps the notification record and clears the task reference.
