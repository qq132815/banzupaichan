# -*- coding: utf-8 -*-
import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "production.db")

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def init_database():
    conn = get_connection()
    c = conn.cursor()

    # ---- Core tables ----
    c.execute("CREATE TABLE IF NOT EXISTS teams (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, leader TEXT, members TEXT, shift_type TEXT, shift_start TEXT, shift_end TEXT)")

    c.execute("CREATE TABLE IF NOT EXISTS equipments (id INTEGER PRIMARY KEY AUTOINCREMENT, equipment_code TEXT NOT NULL UNIQUE, equipment_name TEXT NOT NULL, team_id INTEGER, equipment_type TEXT, status TEXT, capacity_per_hour REAL, location TEXT)")

    c.execute("CREATE TABLE IF NOT EXISTS products (id INTEGER PRIMARY KEY AUTOINCREMENT, product_code TEXT NOT NULL UNIQUE, product_name TEXT, product_type TEXT, safety_stock REAL, unit TEXT)")

    c.execute("CREATE TABLE IF NOT EXISTS work_orders (id INTEGER PRIMARY KEY AUTOINCREMENT, order_no TEXT, product_code TEXT, product_name TEXT, quantity REAL, completed_qty REAL, due_date TEXT, priority TEXT, status TEXT, source TEXT, parent_order_no TEXT, route_code TEXT, process_progress TEXT, create_time TEXT)")

    c.execute("CREATE TABLE IF NOT EXISTS process_routes (id INTEGER PRIMARY KEY AUTOINCREMENT, route_code TEXT, route_name TEXT, product_code TEXT, process_list TEXT, remark TEXT)")

    c.execute("CREATE TABLE IF NOT EXISTS processes (id INTEGER PRIMARY KEY AUTOINCREMENT, process_code TEXT NOT NULL UNIQUE, process_name TEXT, team_name TEXT)")

    c.execute("CREATE TABLE IF NOT EXISTS process_equipment (id INTEGER PRIMARY KEY AUTOINCREMENT, process_code TEXT NOT NULL, equipment_id INTEGER NOT NULL, is_primary INTEGER DEFAULT 1, setup_time INTEGER DEFAULT 0)")

    c.execute("""CREATE TABLE IF NOT EXISTS schedules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        daily_plan_id INTEGER,
        equipment_id INTEGER,
        work_order_no TEXT,
        product_code TEXT,
        process_code TEXT,
        process_name TEXT,
        schedule_date TEXT,
        start_time TEXT,
        end_time TEXT,
        quantity REAL,
        hours REAL,
        capacity_per_hour REAL,
        is_overtime INTEGER,
        team_id INTEGER,
        task_status TEXT,
        priority TEXT,
        operator TEXT,
        created_at TEXT DEFAULT (datetime('now','localtime')),
        FOREIGN KEY (daily_plan_id) REFERENCES daily_plans(id)
    )""")

    c.execute("CREATE TABLE IF NOT EXISTS reports (id INTEGER PRIMARY KEY AUTOINCREMENT, work_order_no TEXT, process_code TEXT, equipment_id INTEGER, team_id INTEGER, report_date TEXT, planned_qty REAL, actual_qty REAL, operator TEXT)")

    c.execute("CREATE TABLE IF NOT EXISTS shipping_plan (id INTEGER PRIMARY KEY AUTOINCREMENT, product_code TEXT NOT NULL, quantity REAL, ship_date TEXT, k3_order_no TEXT)")

    c.execute("CREATE TABLE IF NOT EXISTS production_cycles (id INTEGER PRIMARY KEY AUTOINCREMENT, product_code TEXT NOT NULL, production_days REAL, lead_days REAL)")

    c.execute("CREATE TABLE IF NOT EXISTS bom (id INTEGER PRIMARY KEY AUTOINCREMENT, parent_product_code TEXT, parent_product_name TEXT, child_product_code TEXT, child_product_name TEXT, quantity REAL, unit TEXT, process_team TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS standard_hours (id INTEGER PRIMARY KEY AUTOINCREMENT, product_code TEXT NOT NULL, product_name TEXT, process_name TEXT NOT NULL, team_name TEXT, standard_hours REAL DEFAULT 0, setup_time REAL DEFAULT 0, remark TEXT, created_at TEXT DEFAULT (datetime('now','localtime')), UNIQUE(product_code, process_name))")

    c.execute("CREATE TABLE IF NOT EXISTS work_reports (id INTEGER PRIMARY KEY AUTOINCREMENT, report_qty REAL, good_qty REAL, bad_qty REAL, report_unit TEXT, good_rate TEXT, operator TEXT, start_time TEXT, end_time TEXT, approve_status TEXT, approver TEXT, approve_time TEXT, creator TEXT, create_time TEXT, process_name TEXT, order_no TEXT, product_code TEXT, product_name TEXT, related_no TEXT, equipment TEXT, report_hours REAL, weld_count REAL, attendance_note TEXT, created_at TEXT DEFAULT (datetime('now','localtime')))")

    c.execute("CREATE TABLE IF NOT EXISTS attendance (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, name TEXT NOT NULL, work_date TEXT NOT NULL, check_in TEXT, check_out TEXT, work_hours REAL DEFAULT 0, plan_hours REAL DEFAULT 8, is_overtime INTEGER DEFAULT 0, leave_type TEXT, created_at TEXT DEFAULT (datetime('now','localtime')), UNIQUE(user_id, work_date))")

    c.execute("CREATE TABLE IF NOT EXISTS system_settings (key TEXT PRIMARY KEY, value TEXT, updated_at TEXT DEFAULT (datetime('now','localtime')))")

    # Insert default publish time if not exists
    c.execute("INSERT OR IGNORE INTO system_settings (key, value) VALUES ('plan_publish_time', '15:00')")

    c.execute("CREATE TABLE IF NOT EXISTS personnel (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, name TEXT NOT NULL, department TEXT, position TEXT, team_id INTEGER, is_active INTEGER DEFAULT 1, created_at TEXT DEFAULT (datetime('now','localtime')))")

    c.execute("CREATE TABLE IF NOT EXISTS molds (id INTEGER PRIMARY KEY AUTOINCREMENT, mold_code TEXT NOT NULL UNIQUE, mold_name TEXT, mold_type TEXT, product_code TEXT, status TEXT DEFAULT 'normal', location TEXT, team_id INTEGER, remark TEXT, created_at TEXT DEFAULT (datetime('now','localtime')))")

    c.execute("CREATE TABLE IF NOT EXISTS alerts (id INTEGER PRIMARY KEY AUTOINCREMENT, product_code TEXT, order_no TEXT, alert_level TEXT, due_date TEXT, quantity REAL, scheduled_qty REAL, shortage_qty REAL, days_remaining INTEGER, message TEXT, status TEXT)")

    # ---- User & Auth tables ----
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        password TEXT NOT NULL,
        display_name TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'team',
        team_id INTEGER,
        is_active INTEGER DEFAULT 1,
        created_at TEXT DEFAULT (datetime('now','localtime'))
    )""")

    # ---- Daily Plan (one per team per day) ----
    c.execute("""CREATE TABLE IF NOT EXISTS daily_plans (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        team_id INTEGER NOT NULL,
        plan_date TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'draft',
        created_by INTEGER,
        submitted_at TEXT,
        approved_by INTEGER,
        approved_at TEXT,
        reject_reason TEXT,
        created_at TEXT DEFAULT (datetime('now','localtime')),
        UNIQUE(team_id, plan_date)
    )""")

    # ---- Production Requirements (from shipping plan back-calculation) ----
    c.execute("""CREATE TABLE IF NOT EXISTS production_requirements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_code TEXT,
        product_name TEXT,
        ship_date TEXT,
        ship_quantity REAL,
        required_date TEXT,
        required_quantity REAL,
        team_name TEXT,
        process_name TEXT,
        status TEXT DEFAULT 'draft',
        published_at TEXT,
        published_by TEXT,
        bom_level INTEGER DEFAULT 0,
        root_product TEXT DEFAULT '',
        parent_chain TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS publish_batches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        batch_no TEXT NOT NULL,
        published_at TEXT NOT NULL,
        total_count INTEGER DEFAULT 0,
        total_quantity REAL DEFAULT 0,
        published_by TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")

    # ---- Indexes ----
    c.execute("CREATE INDEX IF NOT EXISTS idx_sp_date ON shipping_plan(ship_date)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_alert_lvl ON alerts(alert_level)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_schedule_date ON schedules(schedule_date)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_schedule_team ON schedules(team_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_schedule_plan ON schedules(daily_plan_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_daily_plan ON daily_plans(team_id, plan_date)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_users_role ON users(role)")

    conn.commit()
    conn.close()
    print("Database initialized")

# ========== User functions ==========
def authenticate_user(username, password):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT u.*, t.name as team_name FROM users u LEFT JOIN teams t ON u.team_id=t.id WHERE u.username=? AND u.password=? AND u.is_active=1", (username, password))
    user = c.fetchone()
    conn.close()
    return dict(user) if user else None

def get_all_users():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT u.*, t.name as team_name FROM users u LEFT JOIN teams t ON u.team_id=t.id ORDER BY u.role, u.id")
    r = [dict(row) for row in c.fetchall()]
    conn.close()
    return r

def create_user(username, password, display_name, role, team_id=None):
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO users (username, password, display_name, role, team_id) VALUES (?,?,?,?,?)",
                  (username, password, display_name, role, team_id))
        conn.commit()
        return c.lastrowid
    except Exception as e:
        return None
    finally:
        conn.close()

def update_user(uid, display_name, role, team_id=None, is_active=1):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE users SET display_name=?, role=?, team_id=?, is_active=? WHERE id=?",
              (display_name, role, team_id, is_active, uid))
    conn.commit()
    conn.close()

def delete_user(uid):
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM users WHERE id=?", (uid,))
    conn.commit()
    conn.close()

def reset_password(uid, new_password):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE users SET password=? WHERE id=?", (new_password, uid))
    conn.commit()
    conn.close()

# ========== Daily Plan functions ==========
def get_or_create_daily_plan(team_id, plan_date):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM daily_plans WHERE team_id=? AND plan_date=?", (team_id, plan_date))
    plan = c.fetchone()
    if plan:
        conn.close()
        return dict(plan)
    c.execute("INSERT INTO daily_plans (team_id, plan_date, status) VALUES (?,?, 'draft')", (team_id, plan_date))
    conn.commit()
    new_id = c.lastrowid
    c.execute("SELECT * FROM daily_plans WHERE id=?", (new_id,))
    plan = dict(c.fetchone())
    conn.close()
    return plan

def get_daily_plan_by_id(plan_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT dp.*, t.name as team_name FROM daily_plans dp LEFT JOIN teams t ON dp.team_id=t.id WHERE dp.id=?", (plan_id,))
    plan = c.fetchone()
    conn.close()
    return dict(plan) if plan else None

def get_all_daily_plans(date=None, team_id=None, date_from=None, date_to=None):
    conn = get_connection()
    c = conn.cursor()
    q = "SELECT dp.*, t.name as team_name FROM daily_plans dp LEFT JOIN teams t ON dp.team_id=t.id WHERE 1=1"
    params = []
    if date:
        q += " AND dp.plan_date=?"
        params.append(date)
    if date_from:
        q += " AND dp.plan_date>=?"
        params.append(date_from)
    if date_to:
        q += " AND dp.plan_date<=?"
        params.append(date_to)
    if team_id:
        q += " AND dp.team_id=?"
        params.append(team_id)
    q += " ORDER BY dp.plan_date DESC, dp.team_id"
    c.execute(q, params)
    r = [dict(row) for row in c.fetchall()]
    conn.close()
    return r

def submit_daily_plan(plan_id, user_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE daily_plans SET status='submitted', submitted_at=datetime('now','localtime') WHERE id=? AND status IN ('draft','returned')", (plan_id,))
    conn.commit()
    conn.close()

def approve_daily_plan(plan_id, user_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE daily_plans SET status='approved', approved_by=?, approved_at=datetime('now','localtime') WHERE id=? AND status='submitted'", (user_id, plan_id))
    conn.commit()
    conn.close()

def reject_daily_plan(plan_id, user_id, reason=''):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE daily_plans SET status='rejected', approved_by=?, approved_at=datetime('now','localtime'), reject_reason=? WHERE id=? AND status='submitted'", (user_id, plan_id, reason))
    conn.commit()
    conn.close()

def return_daily_plan(plan_id, user_id, reason=''):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE daily_plans SET status='returned', reject_reason=? WHERE id=? AND status IN ('submitted','approved')", (reason, plan_id))
    conn.commit()
    conn.close()

# ========== Team & Equipment functions ==========
def get_all_teams():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM teams ORDER BY id")
    r = [dict(row) for row in c.fetchall()]
    conn.close()
    return r

def get_all_equipments(team_id=None, q=None):
    conn = get_connection()
    c = conn.cursor()
    sql = "SELECT * FROM equipments WHERE 1=1"
    params = []
    if team_id:
        sql += " AND team_id=?"
        params.append(team_id)
    if q:
        like = "%" + q + "%"
        sql += " AND (equipment_code LIKE ? OR equipment_name LIKE ? OR location LIKE ?)"
        params.extend([like, like, like])
    sql += " ORDER BY team_id, equipment_code"
    c.execute(sql, params)
    r = [dict(row) for row in c.fetchall()]
    conn.close()
    return r

# ========== Alert functions ==========
def get_alerts(level=None, limit=50):
    conn = get_connection()
    c = conn.cursor()
    if level:
        c.execute("SELECT * FROM alerts WHERE alert_level=? AND status=? ORDER BY due_date LIMIT ?", (level, "active", limit))
    else:
        c.execute("SELECT * FROM alerts WHERE status=? ORDER BY due_date LIMIT ?", ("active", limit))
    r = [dict(row) for row in c.fetchall()]
    conn.close()
    return r

def get_dashboard_stats():
    conn = get_connection()
    c = conn.cursor()
    stats = {}
    c.execute("SELECT COUNT(*) FROM alerts WHERE alert_level=? AND status=?", ("red", "active"))
    stats["red_alerts"] = c.fetchone()[0]
    today = datetime.now().strftime("%Y-%m-%d")
    c.execute("SELECT COUNT(*) FROM schedules WHERE schedule_date=?", (today,))
    stats["today_schedules"] = c.fetchone()[0]
    c.execute("SELECT COUNT(DISTINCT order_no) FROM work_orders WHERE status=?", ("in_progress",))
    stats["in_progress_orders"] = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM alerts WHERE status=?", ("active",))
    stats["total_alerts"] = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM daily_plans WHERE plan_date=? AND status='submitted'", (today,))
    stats["pending_approvals"] = c.fetchone()[0]
    conn.close()
    return stats

if __name__ == "__main__":
    init_database()
