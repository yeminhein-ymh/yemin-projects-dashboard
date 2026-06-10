CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_name TEXT NOT NULL,
    client_name TEXT NOT NULL,
    project_manager TEXT NOT NULL,
    project_director TEXT NOT NULL DEFAULT '',
    portfolio TEXT NOT NULL DEFAULT 'Engineering',
    template_name TEXT NOT NULL DEFAULT 'Standard Project',
    priority TEXT NOT NULL DEFAULT 'Medium',
    start_date TEXT NOT NULL,
    target_completion_date TEXT NOT NULL,
    baseline_start TEXT,
    baseline_finish TEXT,
    actual_start TEXT,
    actual_finish TEXT,
    status TEXT NOT NULL DEFAULT 'Not Started',
    progress INTEGER NOT NULL DEFAULT 0,
    budget REAL NOT NULL DEFAULT 0,
    actual_cost REAL NOT NULL DEFAULT 0,
    forecast_cost REAL NOT NULL DEFAULT 0,
    health_score INTEGER NOT NULL DEFAULT 80,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    parent_task_id INTEGER,
    task_type TEXT NOT NULL DEFAULT 'Daily',
    task_name TEXT NOT NULL,
    owner TEXT NOT NULL,
    start_date TEXT NOT NULL,
    due_date TEXT NOT NULL,
    baseline_start TEXT,
    baseline_finish TEXT,
    actual_start TEXT,
    actual_completion_date TEXT,
    status TEXT NOT NULL DEFAULT 'Not Started',
    progress INTEGER NOT NULL DEFAULT 0,
    weight REAL NOT NULL DEFAULT 1,
    dependency_ids TEXT DEFAULT '',
    is_critical INTEGER NOT NULL DEFAULT 0,
    remarks TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (parent_task_id) REFERENCES tasks(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS team_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    role TEXT NOT NULL,
    user_role TEXT NOT NULL DEFAULT 'Engineer',
    email TEXT,
    phone TEXT,
    capacity_hours REAL NOT NULL DEFAULT 40,
    allocated_hours REAL NOT NULL DEFAULT 32,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS schedules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    activity_name TEXT NOT NULL,
    planned_start TEXT NOT NULL,
    planned_finish TEXT NOT NULL,
    baseline_start TEXT,
    baseline_finish TEXT,
    actual_start TEXT,
    actual_finish TEXT,
    delay_days INTEGER NOT NULL DEFAULT 0,
    progress INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'Not Started',
    remarks TEXT,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS risk_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'Project',
    severity TEXT NOT NULL,
    probability TEXT NOT NULL DEFAULT 'Medium',
    owner TEXT NOT NULL,
    status TEXT NOT NULL,
    mitigation_plan TEXT NOT NULL,
    due_date TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS issues (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'Medium',
    owner TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'Open',
    resolution_plan TEXT NOT NULL,
    due_date TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS budget_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    cost_code TEXT NOT NULL,
    category TEXT NOT NULL,
    budget REAL NOT NULL DEFAULT 0,
    actual REAL NOT NULL DEFAULT 0,
    committed REAL NOT NULL DEFAULT 0,
    forecast REAL NOT NULL DEFAULT 0,
    owner TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS milestones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    milestone_name TEXT NOT NULL,
    due_date TEXT NOT NULL,
    baseline_date TEXT,
    actual_date TEXT,
    status TEXT NOT NULL DEFAULT 'Not Started',
    owner TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS authority_submissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    authority TEXT NOT NULL,
    package_name TEXT NOT NULL,
    owner TEXT NOT NULL,
    target_date TEXT NOT NULL,
    submitted_date TEXT,
    approval_date TEXT,
    status TEXT NOT NULL DEFAULT 'Not Started',
    reference_no TEXT DEFAULT '',
    remarks TEXT,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    folder TEXT NOT NULL DEFAULT 'General',
    file_name TEXT NOT NULL,
    version TEXT NOT NULL DEFAULT 'v1',
    file_path TEXT NOT NULL,
    uploaded_by TEXT NOT NULL,
    uploaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS meetings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    meeting_date TEXT NOT NULL,
    title TEXT NOT NULL,
    attendees TEXT NOT NULL DEFAULT '',
    decisions TEXT NOT NULL DEFAULT '',
    actions TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS email_settings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sender_email TEXT NOT NULL,
    receiver_email TEXT NOT NULL,
    smtp_server TEXT NOT NULL,
    smtp_port INTEGER NOT NULL,
    use_tls INTEGER NOT NULL DEFAULT 1,
    is_active INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS email_notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER,
    receiver_email TEXT NOT NULL,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    status TEXT NOT NULL,
    error_message TEXT,
    sent_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE SET NULL
);
