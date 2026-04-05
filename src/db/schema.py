"""全テーブル DDL 定義"""

CREATE_PERIODS = """
CREATE TABLE IF NOT EXISTS periods (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    submission_deadline TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'collecting'
        CHECK (status IN ('collecting', 'editing', 'archived')),
    form_url TEXT,
    spreadsheet_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

CREATE_STAFF = """
CREATE TABLE IF NOT EXISTS staff (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    employment_type TEXT NOT NULL CHECK (employment_type IN ('part_time', 'employee')),
    hourly_wage REAL NOT NULL CHECK (hourly_wage >= 0),
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

CREATE_SUBMISSIONS = """
CREATE TABLE IF NOT EXISTS submissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period_id INTEGER NOT NULL,
    staff_id INTEGER,
    raw_staff_name TEXT NOT NULL,
    external_submission_key TEXT NOT NULL UNIQUE,
    submitted_at TEXT NOT NULL,
    note_text TEXT,
    weekly_pref_min INTEGER,
    weekly_pref_max INTEGER,
    apply_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (apply_status IN ('pending', 'applied', 'on_hold', 'rejected')),
    is_latest_for_staff INTEGER NOT NULL DEFAULT 0 CHECK (is_latest_for_staff IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK (weekly_pref_max IS NULL OR weekly_pref_min IS NULL OR weekly_pref_min <= weekly_pref_max),
    FOREIGN KEY (period_id) REFERENCES periods(id),
    FOREIGN KEY (staff_id) REFERENCES staff(id)
);
"""

CREATE_SUBMISSION_DAY_ENTRIES = """
CREATE TABLE IF NOT EXISTS submission_day_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    submission_id INTEGER NOT NULL,
    work_date TEXT NOT NULL,
    start_time REAL,
    end_time REAL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(submission_id, work_date),
    FOREIGN KEY (submission_id) REFERENCES submissions(id)
);
"""

CREATE_WISH_SHIFTS = """
CREATE TABLE IF NOT EXISTS wish_shifts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period_id INTEGER NOT NULL,
    staff_id INTEGER NOT NULL,
    work_date TEXT NOT NULL,
    start_time REAL NOT NULL,
    end_time REAL NOT NULL,
    submission_id INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(period_id, staff_id, work_date),
    FOREIGN KEY (period_id) REFERENCES periods(id),
    FOREIGN KEY (staff_id) REFERENCES staff(id),
    FOREIGN KEY (submission_id) REFERENCES submissions(id)
);
"""

CREATE_EDITED_SHIFTS = """
CREATE TABLE IF NOT EXISTS edited_shifts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period_id INTEGER NOT NULL,
    staff_id INTEGER NOT NULL,
    work_date TEXT NOT NULL,
    start_time REAL,
    end_time REAL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(period_id, staff_id, work_date),
    FOREIGN KEY (period_id) REFERENCES periods(id),
    FOREIGN KEY (staff_id) REFERENCES staff(id)
);
"""

CREATE_MANAGER_MEMOS = """
CREATE TABLE IF NOT EXISTS manager_memos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period_id INTEGER NOT NULL,
    staff_id INTEGER NOT NULL,
    work_date TEXT NOT NULL,
    memo_text TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(period_id, staff_id, work_date),
    FOREIGN KEY (period_id) REFERENCES periods(id),
    FOREIGN KEY (staff_id) REFERENCES staff(id)
);
"""

CREATE_CELL_MARKS = """
CREATE TABLE IF NOT EXISTS cell_marks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period_id INTEGER NOT NULL,
    staff_id INTEGER NOT NULL,
    work_date TEXT NOT NULL,
    mark_color TEXT NOT NULL CHECK (mark_color IN ('red', 'yellow')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(period_id, staff_id, work_date),
    FOREIGN KEY (period_id) REFERENCES periods(id),
    FOREIGN KEY (staff_id) REFERENCES staff(id)
);
"""

CREATE_CUSTOM_DAY_RULES = """
CREATE TABLE IF NOT EXISTS custom_day_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period_id INTEGER NOT NULL DEFAULT 0,
    rule_date TEXT NOT NULL,
    is_custom_holiday INTEGER NOT NULL DEFAULT 0 CHECK (is_custom_holiday IN (0, 1)),
    exclude_auto_holiday INTEGER NOT NULL DEFAULT 0 CHECK (exclude_auto_holiday IN (0, 1)),
    wage_bonus REAL CHECK (wage_bonus IS NULL OR wage_bonus >= 0),
    note_text TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(period_id, rule_date)
);
"""

CREATE_APP_SETTINGS = """
CREATE TABLE IF NOT EXISTS app_settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    schema_version INTEGER NOT NULL DEFAULT 1,
    day_shift_start REAL NOT NULL DEFAULT 8,
    day_shift_end REAL NOT NULL DEFAULT 17,
    night_shift_start REAL NOT NULL DEFAULT 17,
    night_shift_end REAL NOT NULL DEFAULT 22,
    overlap_hours_threshold REAL NOT NULL DEFAULT 2,
    saturday_bonus REAL NOT NULL DEFAULT 100 CHECK (saturday_bonus >= 0),
    sunday_bonus REAL NOT NULL DEFAULT 100 CHECK (sunday_bonus >= 0),
    holiday_bonus REAL NOT NULL DEFAULT 100 CHECK (holiday_bonus >= 0),
    weekday_day_min_staff INTEGER NOT NULL DEFAULT 2 CHECK (weekday_day_min_staff >= 0),
    weekday_night_min_staff INTEGER NOT NULL DEFAULT 2 CHECK (weekday_night_min_staff >= 0),
    weekend_day_min_staff INTEGER NOT NULL DEFAULT 5 CHECK (weekend_day_min_staff >= 0),
    weekend_night_min_staff INTEGER NOT NULL DEFAULT 3 CHECK (weekend_night_min_staff >= 0),
    print_font_size INTEGER NOT NULL DEFAULT 9 CHECK (print_font_size >= 1),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

CREATE_PERIOD_PRINT_SETTINGS = """
CREATE TABLE IF NOT EXISTS period_print_settings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period_id INTEGER NOT NULL UNIQUE,
    print_from_date TEXT,
    print_to_date TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (period_id) REFERENCES periods(id)
);
"""

ALL_DDL: list[str] = [
    CREATE_PERIODS,
    CREATE_STAFF,
    CREATE_SUBMISSIONS,
    CREATE_SUBMISSION_DAY_ENTRIES,
    CREATE_WISH_SHIFTS,
    CREATE_EDITED_SHIFTS,
    CREATE_MANAGER_MEMOS,
    CREATE_CELL_MARKS,
    CREATE_CUSTOM_DAY_RULES,
    CREATE_APP_SETTINGS,
    CREATE_PERIOD_PRINT_SETTINGS,
]
