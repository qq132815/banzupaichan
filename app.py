# -*- coding: utf-8 -*-
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import os
import sys
import threading
import subprocess
from datetime import datetime, timedelta
from functools import wraps

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from utils.db import (init_database, get_all_teams, get_all_equipments, get_alerts,
                       get_dashboard_stats, get_connection, authenticate_user,
                       get_all_users, create_user, update_user, delete_user, reset_password,
                       get_or_create_daily_plan, get_daily_plan_by_id, get_all_daily_plans,
                       submit_daily_plan, approve_daily_plan, reject_daily_plan, return_daily_plan)
from utils.excel import (import_shipping_plan, import_production_cycles,
                          import_work_orders, import_processes, import_bom)
from utils.calc import (calculate_alerts, back_calculate_semi, calculate_quantity,
                       calculate_production_requirements, publish_requirements, get_published_requirements)

app = Flask(__name__)

# ========== MES Sync Scheduler ==========
_sync_scheduler_running = False

def _run_attendance_sync(date_from, date_to):
    """Run attendance sync in background thread."""
    try:
        from utils.attendance_api import sync_attendance
        count = sync_attendance(date_from, date_to)
        print(f"[attendance] Auto-sync completed: {count} records for {date_from}~{date_to}")
    except Exception as e:
        print(f"[attendance] Auto-sync error: {e}")

def _run_sync_job(sync_type):
    """Run sync job in background thread."""
    try:
        script = os.path.join(os.path.dirname(__file__), 'scripts', f'sync_{sync_type}.py')
        result = subprocess.run(
            [sys.executable, script],
            capture_output=True, text=True, timeout=300,
            cwd=os.path.dirname(__file__)
        )
        print(f"[{sync_type}] Sync completed: {result.stdout[-200:]}")
    except Exception as e:
        print(f"[{sync_type}] Sync error: {e}")

def _sync_scheduler():
    """Background scheduler that checks and runs sync jobs."""
    global _sync_scheduler_running
    _sync_scheduler_running = True
    import time
    last_run = {'work_orders': 0, 'reports': 0, 'attendance': 0}
    
    while _sync_scheduler_running:
        try:
            conn = get_connection()
            c = conn.cursor()
            c.execute("SELECT key, value FROM system_settings WHERE key IN ('mes_work_order_interval','mes_report_interval')")
            settings = {r[0]: int(r[1]) for r in c.fetchall() if r[1].isdigit()}
            conn.close()
            
            wo_interval = settings.get('mes_work_order_interval', 0) * 60
            rpt_interval = settings.get('mes_report_interval', 0) * 60
            now = time.time()
            
            if wo_interval > 0 and now - last_run['work_orders'] >= wo_interval:
                last_run['work_orders'] = now
                t = threading.Thread(target=_run_sync_job, args=('work_orders',))
                t.daemon = True
                t.start()
            
            if rpt_interval > 0 and now - last_run['reports'] >= rpt_interval:
                last_run['reports'] = now
                t = threading.Thread(target=_run_sync_job, args=('reports',))
                t.daemon = True
                t.start()
            
            # Attendance auto-sync at 8:30 AM daily
            try:
                conn2 = get_connection()
                c2 = conn2.cursor()
                c2.execute("SELECT value FROM system_settings WHERE key='attendance_auto_sync'")
                auto_row = c2.fetchone()
                auto_sync = int(auto_row[0]) if auto_row and auto_row[0].isdigit() else 0
                conn2.close()
                
                if auto_sync:
                    now_dt = datetime.now()
                    today_830 = now_dt.replace(hour=8, minute=30, second=0, microsecond=0)
                    # Run if it's between 8:30 and 8:35 and hasn't run today at 8:30
                    last_att = last_run.get('attendance', 0)
                    if now_dt >= today_830 and now_dt < today_830.replace(minute=35):
                        if time.time() - last_att > 3600:  # at least 1 hour since last run
                            last_run['attendance'] = time.time()
                            yesterday = (now_dt - timedelta(days=1)).strftime('%Y-%m-%d')
                            t = threading.Thread(target=_run_attendance_sync, args=(yesterday, yesterday))
                            t.daemon = True
                            t.start()
                            print(f"[attendance] Auto-sync triggered for {yesterday}")
            except Exception as e:
                print(f"Attendance auto-sync error: {e}")
            
            time.sleep(60)
        except Exception as e:
            print(f"Scheduler error: {e}")
            time.sleep(60)

# Start scheduler in background
_scheduler_thread = threading.Thread(target=_sync_scheduler)
_scheduler_thread.daemon = True
_scheduler_thread.start()


def paginate_query(sql, params, page=1, page_size=50):
    """Execute a paginated query. Returns dict with data, total, page info."""
    conn = get_connection()
    c = conn.cursor()
    # Count total
    count_sql = "SELECT COUNT(*) FROM (" + sql + ")"
    c.execute(count_sql, params)
    total = c.fetchone()[0]
    # Apply pagination
    page = max(1, int(page or 1))
    page_size = min(200, max(1, int(page_size or 50)))
    offset = (page - 1) * page_size
    sql += " LIMIT ? OFFSET ?"
    params.extend([page_size, offset])
    c.execute(sql, params)
    data = [dict(row) for row in c.fetchall()]
    conn.close()
    total_pages = max(1, (total + page_size - 1) // page_size)
    return {"data": data, "total": total, "page": page, "page_size": page_size, "total_pages": total_pages}


app.secret_key = 'mes-scheduling-secret-2026'
app.config["UPLOAD_FOLDER"] = os.path.join(os.path.dirname(__file__), "imports")

# ========== Auth Decorators ==========
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            if request.path.startswith('/api/'):
                return jsonify({'error': 'unauthorized'}), 401
            return redirect('/login')
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get('role') != 'admin':
            return jsonify({'error': 'forbidden'}), 403
        return f(*args, **kwargs)
    return decorated

def planner_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get('role') not in ('planner', 'admin'):
            return jsonify({'error': 'forbidden'}), 403
        return f(*args, **kwargs)
    return decorated

# ========== Login/Logout ==========
@app.route('/login')
def login_page():
    if 'user_id' in session:
        return redirect('/')
    return render_template('login.html')

@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.json
    user = authenticate_user(data.get('username',''), data.get('password',''))
    if not user:
        return jsonify({'error': '用户名或密码错误'}), 401
    session['user_id'] = user['id']
    session['username'] = user['username']
    session['display_name'] = user['display_name']
    session['role'] = user['role']
    session['team_id'] = user['team_id']
    session['team_name'] = user.get('team_name', '')
    return jsonify({'ok': True, 'user': {
        'id': user['id'], 'username': user['username'],
        'display_name': user['display_name'], 'role': user['role'],
        'team_id': user['team_id'], 'team_name': user.get('team_name', '')
    }})

@app.route('/api/logout', methods=['POST'])
def api_logout():
    session.clear()
    return jsonify({'ok': True})

@app.route('/api/me')
@login_required
def api_me():
    return jsonify({
        'id': session['user_id'], 'username': session['username'],
        'display_name': session['display_name'], 'role': session['role'],
        'team_id': session['team_id']
    })

# ========== Page Routes ==========
@app.route('/')
@login_required
def index():
    return render_template('index.html')

@app.route('/alerts-page')
@login_required
@planner_required
def alerts_page():
    return render_template('alerts.html')

@app.route('/schedule-page')
@login_required
def schedule_page():
    return render_template('schedule.html')

@app.route('/orders-page')
@login_required
@planner_required
def orders_page():
    return render_template('orders.html')

@app.route('/products/processes')
@login_required
def product_processes_page():
    return render_template('product_processes.html')

@app.route('/products/routes')
@login_required
def product_routes_page():
    return render_template('product_routes.html')

@app.route('/products/cycles')
@login_required
def product_cycles_page():
    return render_template('product_cycles.html')

@app.route('/products/bom')
@login_required
def product_bom_page():
    return render_template('product_bom.html')

@app.route('/equipments-page')
@login_required
def equipments_page():
    return render_template('equipments.html')

@app.route('/personnel-page')
@login_required
def personnel_page():
    return render_template('personnel.html')

@app.route('/molds-page')
@login_required
def molds_page():
    return render_template('molds.html')

@app.route('/standard-hours-page')
@login_required
def standard_hours_page():
    return render_template('standard_hours.html')

@app.route('/statistics-page')
@login_required
@admin_required
def statistics_page():
    return render_template('statistics.html')

@app.route('/import-page')
@login_required
def import_page():
    return render_template('import.html')

@app.route('/admin/users')
@login_required
@admin_required
def admin_users_page():
    return render_template('admin_users.html')

@app.route('/admin/settings')
@login_required
@admin_required
def admin_settings_page():
    return render_template('admin_settings.html')

@app.route('/admin/mes-sync')
@login_required
@admin_required
def mes_sync_page():
    return render_template('mes_sync.html')

@app.route('/admin/permissions')
@login_required
@admin_required
def permissions_page():
    return render_template('admin_permissions.html')

@app.route('/work-reports-page')
@login_required
@admin_required
def work_reports_page():
    return render_template('work_reports.html')

@app.route('/reports/efficiency-daily')
@login_required
@admin_required
def report_efficiency_daily_page():
    return render_template('report_efficiency_daily.html')

@app.route('/reports/personal-efficiency')
@login_required
@admin_required
def report_personal_efficiency_page():
    return render_template('report_personal_efficiency.html')

@app.route('/reports/weekly')
@login_required
@admin_required
def report_weekly_page():
    return render_template('report_weekly.html')

@app.route('/reports/monthly')
@login_required
@admin_required
def report_monthly_page():
    return render_template('report_monthly.html')

@app.route('/planner/plans')
@login_required
def planner_plans_page():
    return render_template('planner_plans.html')

@app.route('/api/shipping-plan/template')
@login_required
def api_shipping_plan_template():
    import openpyxl
    from io import BytesIO
    from flask import send_file
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "发货计划"
    # Headers matching the import format: product_code, then date columns
    from datetime import date
    ws.append(["产品编码", "数量", date(2026,6,1), date(2026,6,2), date(2026,6,3)])
    ws.append(["示例产品A", 100, 50, 80, 120])
    ws.append(["示例产品B", 200, 60, 90, 150])
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name="发货计划导入模板.xlsx", mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

@app.route('/planner/shipping-plan')
@login_required
@planner_required
def planner_shipping_plan_page():
    return render_template('planner_shipping_plan.html')

@app.route('/planner/semi-calc')
@login_required
@planner_required
def planner_semi_calc_page():
    return render_template('planner_semi_calc.html')

@app.route('/planner/publish-history')
@login_required
@planner_required
def planner_publish_history_page():
    return render_template('planner_publish_history.html')

@app.route('/schedule-records')
@login_required
def schedule_records_page():
    return render_template('schedule_records.html')

# ========== Dashboard API ==========
@app.route('/api/dashboard')
@login_required
def api_dashboard():
    stats = get_dashboard_stats()
    return jsonify(stats)

# ========== Team API ==========
@app.route('/api/teams')
@login_required
def api_teams():
    return jsonify(get_all_teams())

# ========== Equipment API ==========
@app.route('/api/equipments')
@login_required
def api_equipments():
    team_id = request.args.get('team_id', type=int)
    q = request.args.get('q', '').strip()
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 50, type=int)
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
    return jsonify(paginate_query(sql, params, page, page_size))

@app.route('/api/equipments', methods=['POST'])
@login_required
def api_equipment_create():
    data = request.json
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO equipments (equipment_code, equipment_name, team_id, equipment_type, status, capacity_per_hour, location) VALUES (?, ?, ?, ?, ?, ?, ?)",
                  (data['equipment_code'], data['equipment_name'], data['team_id'],
                   data.get('equipment_type', 'auto'), data.get('status', 'normal'),
                   data.get('capacity_per_hour', 0), data.get('location', '')))
        conn.commit()
        return jsonify({'id': c.lastrowid, 'ok': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 400
    finally:
        conn.close()

@app.route('/api/equipments/<int:eid>', methods=['PUT'])
@login_required
def api_equipment_update(eid):
    data = request.json
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE equipments SET equipment_name=?, team_id=?, equipment_type=?, status=?, capacity_per_hour=?, location=? WHERE id=?",
              (data['equipment_name'], data['team_id'], data.get('equipment_type'),
               data.get('status', 'normal'), data.get('capacity_per_hour', 0),
               data.get('location', ''), eid))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})

@app.route('/api/equipments/<int:eid>', methods=['DELETE'])
@login_required
def api_equipment_delete(eid):
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM equipments WHERE id=?", (eid,))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})

# ========== Alert API ==========
@app.route('/api/alerts')
@login_required
def api_alerts():
    level = request.args.get('level')
    return jsonify(get_alerts(level))

@app.route('/api/alerts/calculate', methods=['POST'])
@login_required
def api_calc_alerts():
    count = calculate_alerts()
    return jsonify({'count': count})

@app.route('/api/back-calculate', methods=['POST'])
@login_required
@planner_required
def api_back_calc():
    count = back_calculate_semi()
    return jsonify({'new_orders': count})

# ========== Import API ==========
@app.route('/api/import/<data_type>', methods=['POST'])
@login_required
def api_import(data_type):
    if 'file' not in request.files:
        return jsonify({'error': 'no file'}), 400
    f = request.files['file']
    path = os.path.join(app.config["UPLOAD_FOLDER"], f.filename)
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    f.save(path)
    try:
        if data_type == 'shipping':
            count = import_shipping_plan(path)
        elif data_type == 'cycles':
            count = import_production_cycles(path)
        elif data_type == 'orders':
            count = import_work_orders(path)
        elif data_type == 'processes':
            count = import_processes(path)
        elif data_type == 'bom':
            count = import_bom(path)
        elif data_type == 'process_routes':
            from utils.excel import import_process_routes
            count = import_process_routes(path)
        elif data_type == 'equipment':
            from utils.excel import import_equipment
            count = import_equipment(path)
        else:
            return jsonify({'error': 'unknown type'}), 400
        return jsonify({'count': count, 'success': True})
    except ValueError as e:
        return jsonify({'error': str(e), 'success': False})
    except Exception as e:
        return jsonify({'error': '导入失败: ' + str(e), 'success': False})

# ========== Daily Plan API ==========
@app.route('/api/daily-plan')
@login_required
def api_daily_plan():
    team_id = request.args.get('team_id', type=int)
    date = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    if not team_id:
        team_id = session.get('team_id')
    if not team_id:
        return jsonify({'error': 'no team'}), 400
    plan = get_or_create_daily_plan(team_id, date)
    return jsonify(plan)

@app.route('/api/daily-plans')
@login_required
def api_daily_plans():
    date = request.args.get('date')
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    team_id = request.args.get('team_id', type=int)
    # Team users can only see their own team's plans
    if session.get('role') == 'team':
        team_id = session.get('team_id')
    return jsonify(get_all_daily_plans(date, team_id, date_from, date_to))

@app.route('/api/daily-plan/<int:pid>/submit', methods=['POST'])
@login_required
def api_submit_plan(pid):
    plan = get_daily_plan_by_id(pid)
    if not plan:
        return jsonify({'error': 'not found'}), 404
    if plan['status'] not in ('draft', 'returned'):
        return jsonify({'error': '当前状态不允许提交'}), 400
    # Check team permission
    if session.get('role') == 'team' and plan['team_id'] != session.get('team_id'):
        return jsonify({'error': '只能提交自己班组的计划'}), 403
    submit_daily_plan(pid, session['user_id'])
    return jsonify({'ok': True})

@app.route('/api/daily-plan/<int:pid>/approve', methods=['POST'])
@login_required
@planner_required
def api_approve_plan(pid):
    approve_daily_plan(pid, session['user_id'])
    return jsonify({'ok': True})

@app.route('/api/daily-plan/<int:pid>/reject', methods=['POST'])
@login_required
@planner_required
def api_reject_plan(pid):
    data = request.json or {}
    reject_daily_plan(pid, session['user_id'], data.get('reason', ''))
    return jsonify({'ok': True})

@app.route('/api/daily-plan/<int:pid>', methods=['DELETE'])
@login_required
def api_delete_daily_plan(pid):
    plan = get_daily_plan_by_id(pid)
    if not plan:
        return jsonify({'error': 'not found'}), 404
    if plan['status'] not in ('draft', 'returned'):
        return jsonify({'error': '只有草稿状态可以删除'}), 400
    if session.get('role') == 'team' and plan['team_id'] != session.get('team_id'):
        return jsonify({'error': '只能删除自己班组的计划'}), 403
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM schedules WHERE daily_plan_id=?", (pid,))
    c.execute("DELETE FROM daily_plans WHERE id=?", (pid,))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})

@app.route('/api/daily-plan/<int:pid>/return', methods=['POST'])
@login_required
def api_return_plan(pid):
    data = request.json or {}
    plan = get_daily_plan_by_id(pid)
    if not plan:
        return jsonify({'error': 'not found'}), 404
    # Planner can return any; team can request return on their own
    if session.get('role') == 'team' and plan['team_id'] != session.get('team_id'):
        return jsonify({'error': '无权操作'}), 403
    return_daily_plan(pid, session['user_id'], data.get('reason', ''))
    return jsonify({'ok': True})

# ========== Schedule API ==========
@app.route('/api/schedule', methods=['GET'])
@login_required
def api_schedule_list():
    conn = get_connection()
    c = conn.cursor()
    team_id = request.args.get('team_id', type=int)
    date = request.args.get('date')
    q = "SELECT s.*, e.equipment_name, e.equipment_code, w.product_name FROM schedules s LEFT JOIN equipments e ON s.equipment_id=e.id LEFT JOIN work_orders w ON s.work_order_no=w.order_no WHERE 1=1"
    params = []
    if team_id:
        q += " AND s.team_id=?"
        params.append(team_id)
    if date:
        q += " AND s.schedule_date=?"
        params.append(date)
    q += " ORDER BY s.start_time"
    c.execute(q, params)
    r = [dict(row) for row in c.fetchall()]
    conn.close()
    return jsonify(r)

@app.route('/api/schedule', methods=['POST'])
@login_required
def api_schedule_create():
    data = request.json
    # Check daily plan status
    plan_date = data.get('schedule_date', datetime.now().strftime('%Y-%m-%d'))
    team_id = data.get('team_id', session.get('team_id'))
    plan = get_or_create_daily_plan(team_id, plan_date)
    if plan['status'] == 'approved':
        return jsonify({'error': '该日计划已审批通过，不能修改。请联系计划员退回。'}), 403
    # Team can only edit their own
    if session.get('role') == 'team' and team_id != session.get('team_id'):
        return jsonify({'error': '只能排自己班组的计划'}), 403

    conn = get_connection()
    c = conn.cursor()
    eq_id = data.get('equipment_id')
    start = data.get('start_time')
    end = data.get('end_time')
    if eq_id and plan_date and start and end:
        c.execute("SELECT id, work_order_no, start_time, end_time FROM schedules WHERE equipment_id=? AND schedule_date=? AND task_status != 'cancelled'",
                  (eq_id, plan_date))
        for ex in c.fetchall():
            if start < (ex["end_time"] or "") and end > (ex["start_time"] or ""):
                conn.close()
                return jsonify({'error': 'conflict', 'conflict_with': ex["work_order_no"],
                                'conflict_time': str(ex["start_time"]) + "-" + str(ex["end_time"])}), 409
    c.execute("INSERT INTO schedules (daily_plan_id, equipment_id, work_order_no, product_code, process_code, process_name, schedule_date, start_time, end_time, quantity, hours, capacity_per_hour, is_overtime, team_id, task_status, priority, operator) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
              (plan['id'], eq_id, data.get('work_order_no'), data.get('product_code'),
               data.get('process_code'), data.get('process_name'), plan_date, start, end,
               data.get('quantity', 0), data.get('hours', 0),
               data.get('capacity_per_hour', 0), data.get('is_overtime', 0),
               team_id, 'planned', data.get('priority', 'P2'),
               data.get('operator', '')))
    conn.commit()
    new_id = c.lastrowid
    conn.close()
    return jsonify({'id': new_id, 'ok': True})

@app.route('/api/schedule/<int:sid>', methods=['PUT'])
@login_required
def api_schedule_update(sid):
    data = request.json
    plan_date = data.get('schedule_date')
    team_id = data.get('team_id', session.get('team_id'))
    if plan_date:
        plan = get_or_create_daily_plan(team_id, plan_date)
        if plan['status'] == 'approved':
            return jsonify({'error': '该日计划已审批通过，不能修改'}), 403

    conn = get_connection()
    c = conn.cursor()
    eq_id = data.get('equipment_id')
    start = data.get('start_time')
    end = data.get('end_time')
    if eq_id and plan_date and start and end:
        c.execute("SELECT id, work_order_no, start_time, end_time FROM schedules WHERE equipment_id=? AND schedule_date=? AND id != ? AND task_status != 'cancelled'",
                  (eq_id, plan_date, sid))
        for ex in c.fetchall():
            if start < (ex["end_time"] or "") and end > (ex["start_time"] or ""):
                conn.close()
                return jsonify({'error': 'conflict', 'conflict_with': ex["work_order_no"]}), 409
    c.execute("UPDATE schedules SET equipment_id=?, start_time=?, end_time=?, quantity=?, hours=?, capacity_per_hour=?, is_overtime=?, operator=?, process_code=?, process_name=?, priority=?, work_order_no=?, schedule_date=?, team_id=?, product_code=? WHERE id=?",
              (eq_id, start, end, data.get('quantity', 0), data.get('hours', 0),
               data.get('capacity_per_hour', 0), data.get('is_overtime', 0),
               data.get('operator', ''), data.get('process_code'),
               data.get('process_name'), data.get('priority', 'P2'),
               data.get('work_order_no'), plan_date, team_id, data.get('product_code'), sid))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})

@app.route('/api/schedule/<int:sid>', methods=['DELETE'])
@login_required
def api_schedule_delete(sid):
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM schedules WHERE id=?", (sid,))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})

# ========== Order API ==========
@app.route('/api/orders')
@login_required
def api_orders():
    status = request.args.get('status')
    keyword = request.args.get('q', '')
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 50, type=int)
    sql = "SELECT * FROM work_orders WHERE 1=1"
    params = []
    if status:
        sql += " AND status=?"
        params.append(status)
    if keyword:
        like = "%" + keyword + "%"
        sql += " AND (order_no LIKE ? OR product_code LIKE ? OR product_name LIKE ?)"
        params.extend([like, like, like])
    sql += " ORDER BY create_time DESC"
    return jsonify(paginate_query(sql, params, page, page_size))

@app.route('/api/orders', methods=['POST'])
@login_required
def api_order_create():
    data = request.json
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT INTO work_orders (order_no, product_code, product_name, quantity, completed_qty, due_date, priority, status, source) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
              (data['order_no'], data['product_code'], data.get('product_name', ''),
               data.get('quantity', 0), data.get('completed_qty', 0),
               data.get('due_date'), data.get('priority', 'P2'),
               data.get('status', 'pending'), data.get('source', '')))
    conn.commit()
    new_id = c.lastrowid
    conn.close()
    return jsonify({'id': new_id, 'ok': True})

@app.route('/api/orders/<int:oid>', methods=['PUT'])
@login_required
def api_order_update(oid):
    data = request.json
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE work_orders SET order_no=?, product_code=?, product_name=?, quantity=?, completed_qty=?, due_date=?, priority=?, status=?, source=? WHERE id=?",
              (data['order_no'], data['product_code'], data.get('product_name', ''),
               data.get('quantity', 0), data.get('completed_qty', 0),
               data.get('due_date'), data.get('priority', 'P2'),
               data.get('status', 'pending'), data.get('source', ''), oid))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})

@app.route('/api/orders/<int:oid>', methods=['DELETE'])
@login_required
def api_order_delete(oid):
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM work_orders WHERE id=?", (oid,))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})

@app.route('/api/orders/clear', methods=['POST'])
@login_required
@planner_required
def api_orders_clear():
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM work_orders")
    deleted = c.rowcount
    conn.commit()
    conn.close()
    return jsonify({'ok': True, 'deleted': deleted})

@app.route('/api/search-orders')
@login_required
def api_search_orders():
    keyword = request.args.get('q', '')
    team_name = session.get('team_name', '')
    conn = get_connection()
    c = conn.cursor()
    if team_name:
        # Get process names belonging to this team
        c.execute("SELECT DISTINCT process_name FROM processes WHERE team_name LIKE ?", ('%' + team_name + '%',))
        team_procs = [r[0] for r in c.fetchall()]
        # Find product_codes whose process_routes contain any of these processes
        matching_products = set()
        c.execute("SELECT product_code, process_list FROM process_routes")
        for r in c.fetchall():
            pc = r[0]
            pl = r[1] or ''
            for tp in team_procs:
                if tp in pl:
                    matching_products.add(pc)
                    break
        if not matching_products:
            conn.close()
            return jsonify([])
        placeholders = ','.join(['?' for _ in matching_products])
        params = ['%' + keyword + '%', '%' + keyword + '%', '%' + keyword + '%'] + list(matching_products)
        c.execute(f"SELECT * FROM work_orders WHERE (order_no LIKE ? OR product_code LIKE ? OR product_name LIKE ?) AND product_code IN ({placeholders}) LIMIT 20", params)
    else:
        c.execute("SELECT * FROM work_orders WHERE order_no LIKE ? OR product_code LIKE ? OR product_name LIKE ? LIMIT 20",
                  ('%' + keyword + '%', '%' + keyword + '%', '%' + keyword + '%'))
    orders = [dict(row) for row in c.fetchall()]
    conn.close()
    return jsonify(orders)

# ========== Product Process API ==========
@app.route('/api/product-processes')
@login_required
def api_product_processes():
    product_code = request.args.get('product_code', '')
    team_name = session.get('team_name', '')
    conn = get_connection()
    c = conn.cursor()
    # Match on product_code column for precise lookup
    c.execute("SELECT route_code, route_name, process_list FROM process_routes WHERE product_code = ?", (product_code,))
    routes = c.fetchall()
    if not routes:
        # Fallback: try route_code exact match
        c.execute("SELECT route_code, route_name, process_list FROM process_routes WHERE route_code = ?", (product_code,))
        routes = c.fetchall()
    result = []
    seen = set()
    for r in routes:
        route_code = r[0]
        route_name = r[1]
        process_list = r[2]
        if process_list:
            for proc_name in process_list.split(','):
                proc_name = proc_name.strip()
                if not proc_name:
                    continue
                key = route_code + '|' + proc_name
                if key in seen:
                    continue
                seen.add(key)
                c.execute("SELECT process_code, team_name FROM processes WHERE process_name=?", (proc_name,))
                proc = c.fetchone()
                if proc:
                    # Filter by team if user is a team member
                    if team_name and proc[1] and team_name not in proc[1]:
                        continue
                    result.append({
                        'route_code': route_code, 'route_name': route_name,
                        'process_code': proc[0], 'process_name': proc_name,
                        'team_name': proc[1]
                    })
    conn.close()
    return jsonify(result)

@app.route('/api/process-equipment')
@login_required
def api_process_equipment():
    process_code = request.args.get('process_code', '')
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT e.id, e.equipment_code, e.equipment_name, e.equipment_type, e.capacity_per_hour, e.location FROM equipments e JOIN process_equipment pe ON e.id = pe.equipment_id WHERE pe.process_code = ?", (process_code,))
    equips = [dict(zip(['id', 'equipment_code', 'equipment_name', 'equipment_type', 'capacity_per_hour', 'location'], row)) for row in c.fetchall()]
    conn.close()
    return jsonify(equips)

# ========== Processes CRUD ==========
@app.route('/api/processes')
@login_required
def api_processes():
    q = request.args.get('q', '')
    team = request.args.get('team', '')
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 50, type=int)
    sql = "SELECT * FROM processes WHERE 1=1"
    params = []
    if q:
        sql += " AND (process_name LIKE ? OR process_code LIKE ?)"
        params.extend(['%'+q+'%', '%'+q+'%'])
    if team:
        sql += " AND team_name LIKE ?"
        params.append('%' + team + '%')
    sql += " ORDER BY team_name, process_code"
    return jsonify(paginate_query(sql, params, page, page_size))

@app.route('/api/processes', methods=['POST'])
@login_required
def api_process_create():
    data = request.json
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO processes (process_code, process_name, team_name) VALUES (?, ?, ?)",
                  (data['process_code'], data['process_name'], data.get('team_name', '')))
        conn.commit()
        return jsonify({'id': c.lastrowid, 'ok': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 400
    finally:
        conn.close()

@app.route('/api/processes/<int:pid>', methods=['PUT'])
@login_required
def api_process_update(pid):
    data = request.json
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE processes SET process_code=?, process_name=?, team_name=? WHERE id=?",
              (data['process_code'], data['process_name'], data.get('team_name', ''), pid))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})

@app.route('/api/processes/<int:pid>', methods=['DELETE'])
@login_required
def api_process_delete(pid):
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM processes WHERE id=?", (pid,))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})

# ========== Production Requirements API ==========
@app.route('/api/production-requirements')
@login_required
def api_production_requirements():
    status = request.args.get('status', '')
    conn = get_connection()
    c = conn.cursor()
    if status:
        c.execute("SELECT * FROM production_requirements WHERE status=? ORDER BY required_date, product_code", (status,))
    else:
        c.execute("SELECT * FROM production_requirements ORDER BY required_date, product_code")
    results = [dict(row) for row in c.fetchall()]
    conn.close()
    return jsonify(results)

@app.route('/api/production-requirements/calculate', methods=['POST'])
@login_required
@planner_required
def api_calculate_requirements():
    count = calculate_production_requirements()
    return jsonify({'count': count})

@app.route('/api/production-requirements/publish', methods=['POST'])
@login_required
@planner_required
def api_publish_requirements():
    data = request.json or {}
    ids = data.get('ids', [])
    count = publish_requirements(ids if ids else None)
    # Create publish batch record
    if count > 0:
        conn = get_connection()
        c = conn.cursor()
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        batch_no = 'PB-' + datetime.now().strftime('%Y%m%d%H%M%S')
        c.execute("SELECT COUNT(*), COALESCE(SUM(required_quantity),0) FROM production_requirements WHERE status='published' AND (batch_id IS NULL OR batch_id=0)", )
        row = c.fetchone()
        total_count = row[0] if row else 0
        total_qty = row[1] if row else 0
        c.execute("INSERT INTO publish_batches (batch_no, published_at, total_count, total_quantity, published_by) VALUES (?,?,?,?,?)",
                  (batch_no, now, total_count, total_qty, session.get('username','')))
        batch_id = c.lastrowid
        c.execute("UPDATE production_requirements SET batch_id=?, published_at=? WHERE status='published' AND (batch_id IS NULL OR batch_id=0)",
                  (batch_id, now))
        conn.commit()
        conn.close()
    return jsonify({'published': count})

@app.route('/api/publish-batches')
@login_required
@planner_required
def api_publish_batches():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM publish_batches ORDER BY published_at DESC")
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return jsonify(rows)

@app.route('/api/publish-batches/<int:batch_id>/details')
@login_required
@planner_required
def api_publish_batch_details(batch_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM production_requirements WHERE batch_id=? ORDER BY parent_chain, required_date", (batch_id,))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return jsonify(rows)

@app.route('/api/schedule-warnings')
@login_required
def api_schedule_warnings():
    team_name = session.get('team_name', '')
    if not team_name:
        team_name = request.args.get('team', '')
    conn = get_connection()
    c = conn.cursor()
    # Get published requirements for this team
    c.execute("""SELECT product_code, product_name, required_date, required_quantity, team_name
        FROM production_requirements WHERE status='published' ORDER BY required_date""")
    rows = c.fetchall()
    # Filter by team (team_name may be comma-separated in requirements)
    filtered = []
    for r in rows:
        tn = r[4] or ''
        if team_name and team_name not in tn:
            continue
        filtered.append({'product_code': r[0], 'product_name': r[1], 'required_date': r[2], 'required_quantity': r[3]})
    # Get incomplete quantities from work_orders
    c.execute("""SELECT product_code, product_name, SUM(COALESCE(quantity,0) - COALESCE(completed_qty,0)) as remaining
        FROM work_orders WHERE status != 'completed' GROUP BY product_code""")
    wo_remaining = {}
    for r in c.fetchall():
        key = r[1] or r[0]  # use product_name first, fallback to code
        wo_remaining[key] = r[2] if r[2] else 0
    conn.close()
    return jsonify({'requirements': filtered, 'work_order_remaining': wo_remaining})

@app.route('/api/production-requirements/for-team')
@login_required
def api_requirements_for_team():
    """Get published requirements for current team"""
    team_name = request.args.get('team', '')
    if not team_name:
        team_name = session.get('team_name', '')
    
    # Date range is optional
    start_date = request.args.get('start', '')
    end_date = request.args.get('end', '')
    
    requirements = get_published_requirements(team_name, start_date if start_date else None, end_date if end_date else None)
    return jsonify(requirements)

@app.route('/api/production-requirements/<int:rid>', methods=['DELETE'])
@login_required
@planner_required
def api_delete_requirement(rid):
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM production_requirements WHERE id=?", (rid,))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})

# ========== Reference Panel APIs ==========
@app.route('/api/reference/semi-finished-output')
@login_required
def api_semi_finished_output():
    """Return work reports from last 2 days for semi-finished product processes.
    Semi-finished = second-to-last process in route (or the only process if just one).
    """
    from datetime import datetime, timedelta
    conn = get_connection()
    c = conn.cursor()

    # 1. Build product_code -> semi-finished process name mapping
    c.execute("SELECT product_code, process_list FROM process_routes WHERE process_list IS NOT NULL AND process_list != ''")
    routes = c.fetchall()
    semi_process_map = {}  # product_code -> set of semi-finished process names
    for pc, pl in routes:
        procs = [p.strip() for p in pl.split(',') if p.strip()]
        if not procs:
            continue
        if len(procs) == 1:
            target = procs[0]
        else:
            target = procs[-2]
        if pc not in semi_process_map:
            semi_process_map[pc] = set()
        semi_process_map[pc].add(target)

    if not semi_process_map:
        conn.close()
        return jsonify([])

    # 2. Get reports from last 2 days (join personnel for team name)
    cutoff = (datetime.now() - timedelta(days=2)).strftime('%Y-%m-%d')
    c.execute("""SELECT r.product_code, r.product_name, r.process_name, r.report_qty, r.good_qty,
                 r.create_time, r.operator, t.name as team_name
                 FROM work_reports r
                 LEFT JOIN personnel p ON r.operator = p.name
                 LEFT JOIN teams t ON p.team_id = t.id
                 WHERE r.create_time >= ?
                 ORDER BY r.create_time DESC""", (cutoff,))
    all_reports = c.fetchall()

    # 3. Filter: keep only reports where process matches semi-finished process for that product
    team_data = {}
    for r in all_reports:
        pc, pn, proc, qty, gqty, ctime, op, team = r
        allowed = semi_process_map.get(pc)
        if allowed and proc in allowed:
            tn = team or '未知班组'
            if tn not in team_data:
                team_data[tn] = []
            team_data[tn].append({
                'product_code': pc or '',
                'product_name': pn or '',
                'process_name': proc or '',
                'report_qty': qty or 0,
                'good_qty': gqty or 0,
                'create_time': ctime or '',
                'operator': op or ''
            })

    conn.close()

    # 4. Format response
    result = []
    for tn in sorted(team_data.keys()):
        result.append({'team': tn, 'records': team_data[tn]})

    return jsonify(result)

# ========== Process Routes CRUD ==========
@app.route('/api/process-routes')
@login_required
def api_process_routes():
    q = request.args.get('q', '').strip()
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 50, type=int)
    sql = "SELECT * FROM process_routes WHERE 1=1"
    params = []
    if q:
        like = "%" + q + "%"
        sql += " AND (route_code LIKE ? OR route_name LIKE ? OR product_code LIKE ? OR process_list LIKE ?)"
        params.extend([like, like, like, like])
    sql += " ORDER BY route_code"
    return jsonify(paginate_query(sql, params, page, page_size))

@app.route('/api/process-routes', methods=['POST'])
@login_required
def api_process_route_create():
    data = request.json
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT INTO process_routes (route_code, route_name, product_code, process_list, remark) VALUES (?,?,?,?,?)",
              (data['route_code'], data.get('route_name',''), data.get('product_code',''), data.get('process_list',''), data.get('remark','')))
    conn.commit()
    new_id = c.lastrowid
    conn.close()
    return jsonify({'id': new_id, 'ok': True})

@app.route('/api/process-routes/<int:rid>', methods=['PUT'])
@login_required
def api_process_route_update(rid):
    data = request.json
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE process_routes SET route_code=?, route_name=?, product_code=?, process_list=?, remark=? WHERE id=?",
              (data['route_code'], data.get('route_name',''), data.get('product_code',''), data.get('process_list',''), data.get('remark',''), rid))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})

@app.route('/api/process-routes/<int:rid>', methods=['DELETE'])
@login_required
def api_process_route_delete(rid):
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM process_routes WHERE id=?", (rid,))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})

# ========== Production Cycles CRUD ==========
@app.route('/api/production-cycles')
@login_required
def api_production_cycles():
    conn = get_connection()
    c = conn.cursor()
    keyword = request.args.get('q', '')
    if keyword:
        c.execute("SELECT * FROM production_cycles WHERE product_code LIKE ? LIMIT 50", ('%' + keyword + '%',))
    else:
        c.execute("SELECT * FROM production_cycles LIMIT 100")
    r = [dict(row) for row in c.fetchall()]
    conn.close()
    return jsonify(r)

@app.route('/api/production-cycles', methods=['POST'])
@login_required
def api_production_cycle_create():
    data = request.json
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT INTO production_cycles (product_code, production_days, lead_days) VALUES (?,?,?)",
              (data['product_code'], data.get('production_days', 1), data.get('lead_days', 0)))
    conn.commit()
    new_id = c.lastrowid
    conn.close()
    return jsonify({'id': new_id, 'ok': True})

@app.route('/api/production-cycles/<int:cid>', methods=['PUT'])
@login_required
def api_production_cycle_update(cid):
    data = request.json
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE production_cycles SET product_code=?, production_days=?, lead_days=? WHERE id=?",
              (data['product_code'], data.get('production_days', 1), data.get('lead_days', 0), cid))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})

@app.route('/api/production-cycles/<int:cid>', methods=['DELETE'])
@login_required
def api_production_cycle_delete(cid):
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM production_cycles WHERE id=?", (cid,))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})

# ========== BOM CRUD ==========
@app.route('/api/bom')
@login_required
def api_bom():
    q = request.args.get('q', '').strip()
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 50, type=int)
    sql = "SELECT * FROM bom WHERE 1=1"
    params = []
    if q:
        like = "%" + q + "%"
        sql += " AND (parent_product_code LIKE ? OR parent_product_name LIKE ? OR child_product_code LIKE ? OR child_product_name LIKE ?)"
        params.extend([like, like, like, like])
    sql += " ORDER BY parent_product_code"
    return jsonify(paginate_query(sql, params, page, page_size))

@app.route('/api/bom', methods=['POST'])
@login_required
def api_bom_create():
    data = request.json
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT INTO bom (parent_product_code, parent_product_name, child_product_code, child_product_name, quantity, unit, process_team) VALUES (?,?,?,?,?,?,?)",
              (data['parent_product_code'], data.get('parent_product_name',''), data.get('child_product_code',''),
               data.get('child_product_name',''), data.get('quantity', 1), data.get('unit',''), data.get('process_team','')))
    conn.commit()
    new_id = c.lastrowid
    conn.close()
    return jsonify({'id': new_id, 'ok': True})

@app.route('/api/bom/<int:bid>', methods=['PUT'])
@login_required
def api_bom_update(bid):
    data = request.json
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE bom SET parent_product_code=?, parent_product_name=?, child_product_code=?, child_product_name=?, quantity=?, unit=?, process_team=? WHERE id=?",
              (data['parent_product_code'], data.get('parent_product_name',''), data.get('child_product_code',''),
               data.get('child_product_name',''), data.get('quantity', 1), data.get('unit',''), data.get('process_team',''), bid))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})

@app.route('/api/bom/<int:bid>', methods=['DELETE'])
@login_required
def api_bom_delete(bid):
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM bom WHERE id=?", (bid,))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})

# ========== Personnel API ==========
@app.route('/api/personnel')
@login_required
def api_personnel():
    team_id = request.args.get('team_id', type=int)
    q = request.args.get('q', '').strip()
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 50, type=int)
    sql = "SELECT * FROM personnel WHERE 1=1"
    params = []
    if team_id:
        sql += " AND team_id=?"
        params.append(team_id)
    if q:
        like = "%" + q + "%"
        sql += " AND (name LIKE ? OR user_id LIKE ? OR department LIKE ? OR position LIKE ?)"
        params.extend([like, like, like, like])
    sql += " ORDER BY team_id, name"
    return jsonify(paginate_query(sql, params, page, page_size))

@app.route('/api/personnel', methods=['POST'])
@login_required
def api_personnel_create():
    data = request.json
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT INTO personnel (user_id, name, department, position, team_id) VALUES (?, ?, ?, ?, ?)",
              (data.get('user_id',''), data['name'], data.get('department',''), data.get('position',''), data.get('team_id')))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})

@app.route('/api/personnel/<int:pid>', methods=['PUT'])
@login_required
def api_personnel_update(pid):
    data = request.json
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE personnel SET user_id=?, name=?, department=?, position=?, team_id=?, is_active=? WHERE id=?",
              (data.get('user_id',''), data['name'], data.get('department',''), data.get('position',''), data.get('team_id'), data.get('is_active',1), pid))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})

@app.route('/api/personnel/<int:pid>', methods=['DELETE'])
@login_required
def api_personnel_delete(pid):
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM personnel WHERE id=?", (pid,))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})

# ========== Molds API ==========
@app.route('/api/molds')
@login_required
def api_molds():
    team_id = request.args.get('team_id', type=int)
    q = request.args.get('q', '').strip()
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 50, type=int)
    sql = "SELECT * FROM molds WHERE 1=1"
    params = []
    if team_id:
        sql += " AND team_id=?"
        params.append(team_id)
    if q:
        like = "%" + q + "%"
        sql += " AND (mold_code LIKE ? OR mold_name LIKE ? OR product_code LIKE ? OR location LIKE ?)"
        params.extend([like, like, like, like])
    sql += " ORDER BY mold_code"
    return jsonify(paginate_query(sql, params, page, page_size))

@app.route('/api/molds', methods=['POST'])
@login_required
def api_molds_create():
    data = request.json
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT INTO molds (mold_code, mold_name, mold_type, product_code, status, location, team_id, remark) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
              (data['mold_code'], data.get('mold_name',''), data.get('mold_type',''), data.get('product_code',''), data.get('status','normal'), data.get('location',''), data.get('team_id'), data.get('remark','')))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})

@app.route('/api/molds/<int:mid>', methods=['PUT'])
@login_required
def api_molds_update(mid):
    data = request.json
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE molds SET mold_code=?, mold_name=?, mold_type=?, product_code=?, status=?, location=?, team_id=?, remark=? WHERE id=?",
              (data['mold_code'], data.get('mold_name',''), data.get('mold_type',''), data.get('product_code',''), data.get('status','normal'), data.get('location',''), data.get('team_id'), data.get('remark',''), mid))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})

@app.route('/api/molds/<int:mid>', methods=['DELETE'])
@login_required
def api_molds_delete(mid):
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM molds WHERE id=?", (mid,))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})

# ========== Personnel & Mold Import ==========
@app.route('/api/import/personnel', methods=['POST'])
@login_required
def api_import_personnel():
    from utils.excel import import_personnel
    f = request.files.get('file')
    if not f:
        return jsonify({'error': '请上传文件'}), 400
    path = os.path.join(app.config['UPLOAD_FOLDER'], f.filename)
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    f.save(path)
    try:
        count = import_personnel(path)
        return jsonify({'ok': True, 'count': count})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/api/import/molds', methods=['POST'])
@login_required
def api_import_molds():
    from utils.excel import import_molds
    f = request.files.get('file')
    if not f:
        return jsonify({'error': '请上传文件'}), 400
    path = os.path.join(app.config['UPLOAD_FOLDER'], f.filename)
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    f.save(path)
    try:
        count = import_molds(path)
        return jsonify({'ok': True, 'count': count})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

# ========== Standard Hours API ==========
@app.route('/api/standard-hours')
@login_required
def api_standard_hours():
    q = request.args.get('q', '').strip()
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 50, type=int)
    sql = "SELECT * FROM standard_hours WHERE 1=1"
    params = []
    if q:
        like = "%" + q + "%"
        sql += " AND (product_code LIKE ? OR product_name LIKE ? OR process_name LIKE ?)"
        params.extend([like, like, like])
    sql += " ORDER BY product_code, process_name"
    return jsonify(paginate_query(sql, params, page, page_size))

@app.route('/api/standard-hours', methods=['POST'])
@login_required
def api_standard_hours_create():
    data = request.json
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO standard_hours (product_code, product_name, process_name, team_name, standard_hours, setup_time, remark) VALUES (?, ?, ?, ?, ?, ?, ?)",
                  (data['product_code'], data.get('product_name',''), data['process_name'], data.get('team_name',''), data.get('standard_hours',0), data.get('setup_time',0), data.get('remark','')))
        conn.commit()
    except Exception as e:
        conn.close()
        return jsonify({'error': str(e)}), 400
    conn.close()
    return jsonify({'ok': True})

@app.route('/api/standard-hours/<int:sid>', methods=['PUT'])
@login_required
def api_standard_hours_update(sid):
    data = request.json
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE standard_hours SET product_code=?, product_name=?, process_name=?, team_name=?, standard_hours=?, setup_time=?, remark=? WHERE id=?",
              (data['product_code'], data.get('product_name',''), data['process_name'], data.get('team_name',''), data.get('standard_hours',0), data.get('setup_time',0), data.get('remark',''), sid))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})

@app.route('/api/standard-hours/<int:sid>', methods=['DELETE'])
@login_required
def api_standard_hours_delete(sid):
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM standard_hours WHERE id=?", (sid,))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})

@app.route('/api/standard-hours/init', methods=['POST'])
@login_required
def api_standard_hours_init():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT DISTINCT product_code, route_name, process_list, remark FROM process_routes WHERE process_list IS NOT NULL AND process_list != ''")
    routes = c.fetchall()
    count = 0
    for route in routes:
        product_code = route[0] or ''
        product_name = route[1] or ''
        process_list = route[2] or ''
        team_name = route[3] or ''
        processes = [p.strip() for p in process_list.split(',') if p.strip()]
        for proc in processes:
            try:
                c.execute("INSERT OR IGNORE INTO standard_hours (product_code, product_name, process_name, team_name) VALUES (?, ?, ?, ?)",
                          (product_code, product_name, proc, team_name))
                if c.rowcount > 0:
                    count += 1
            except:
                pass
    conn.commit()
    conn.close()
    return jsonify({'ok': True, 'count': count})

# ========== Work Reports API ==========
@app.route('/api/work-reports')
@login_required
def api_work_reports():
    q = request.args.get('q', '').strip()
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 50, type=int)
    sql = """SELECT r.*, t.name as team_name FROM work_reports r
              LEFT JOIN personnel p ON r.operator = p.name
              LEFT JOIN teams t ON p.team_id = t.id
              WHERE 1=1"""
    params = []
    date = request.args.get('date', '').strip()
    if date:
        sql += " AND r.create_time LIKE ?"
        params.append(date + '%')
    team_filter = request.args.get('team', '').strip()
    if team_filter:
        sql += " AND t.name = ?"
        params.append(team_filter)
    if q:
        like = "%" + q + "%"
        sql += " AND (r.order_no LIKE ? OR r.product_code LIKE ? OR r.product_name LIKE ? OR r.process_name LIKE ? OR r.operator LIKE ?)"
        params.extend([like, like, like, like, like])
    sql += " ORDER BY r.create_time DESC"
    return jsonify(paginate_query(sql, params, page, page_size))

@app.route('/api/work-reports', methods=['DELETE'])
@login_required
@planner_required
def api_work_reports_clear():
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM work_reports")
    conn.commit()
    conn.close()
    return jsonify({'ok': True})

@app.route('/api/import/work-reports', methods=['POST'])
@login_required
@planner_required
def api_import_work_reports():
    from utils.excel import import_work_reports
    f = request.files.get('file')
    if not f:
        return jsonify({'error': '请上传文件'}), 400
    path = os.path.join(app.config['UPLOAD_FOLDER'], f.filename)
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    f.save(path)
    try:
        count = import_work_reports(path)
        return jsonify({'ok': True, 'success': True, 'count': count})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

# ========== System Settings API ==========
@app.route('/api/settings', methods=['GET'])
@login_required
def api_get_settings():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT key, value FROM system_settings")
    r = {row[0]: row[1] for row in c.fetchall()}
    conn.close()
    return jsonify(r)

@app.route('/api/settings', methods=['POST'])
@login_required
@planner_required
def api_save_settings():
    data = request.json
    conn = get_connection()
    c = conn.cursor()
    for key, value in data.items():
        c.execute("INSERT OR REPLACE INTO system_settings (key, value, updated_at) VALUES (?, ?, datetime('now','localtime'))", (key, str(value)))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})

# ========== Permissions API ==========
@app.route('/api/permissions', methods=['GET'])
@login_required
@admin_required
def api_get_permissions():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT key, value FROM system_settings WHERE key LIKE 'perm_%'")
    rows = c.fetchall()
    conn.close()
    
    permissions = {}
    for row in rows:
        key = row[0].replace('perm_', '')
        try:
            permissions[key] = eval(row[1])
        except:
            permissions[key] = {'admin': True, 'planner': True, 'team': False}
    
    # Default permissions if not set
    defaults = {
        'workbench': {'admin': True, 'planner': True, 'team': True},
        'schedule': {'admin': False, 'planner': False, 'team': True},
        'shipping_plan': {'admin': True, 'planner': True, 'team': False},
        'plan_approval': {'admin': True, 'planner': True, 'team': False},
        'alerts': {'admin': True, 'planner': True, 'team': False},
        'orders': {'admin': True, 'planner': True, 'team': False},
        'basic_data': {'admin': True, 'planner': True, 'team': True},
        'basic_data_edit': {'admin': True, 'planner': True, 'team': False},
        'production_reports': {'admin': True, 'planner': False, 'team': False},
        'system_management': {'admin': True, 'planner': False, 'team': False}
    }
    
    for key, default in defaults.items():
        if key not in permissions:
            permissions[key] = default
    
    return jsonify(permissions)

@app.route('/api/permissions', methods=['POST'])
@login_required
@admin_required
def api_save_permissions():
    data = request.json
    conn = get_connection()
    c = conn.cursor()
    for key, value in data.items():
        c.execute("INSERT OR REPLACE INTO system_settings (key, value, updated_at) VALUES (?, ?, datetime('now','localtime'))", ('perm_' + key, str(value)))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})

# ========== MES Sync API ==========
@app.route('/api/mes-sync/settings', methods=['GET'])
@login_required
@planner_required
def api_get_sync_settings():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT key, value FROM system_settings WHERE key IN ('mes_work_order_interval','mes_report_interval')")
    r = {row[0]: row[1] for row in c.fetchall()}
    conn.close()
    return jsonify({
        'work_order_interval': int(r.get('mes_work_order_interval', 0)),
        'report_interval': int(r.get('mes_report_interval', 0))
    })

@app.route('/api/mes-sync/settings', methods=['POST'])
@login_required
@planner_required
def api_save_sync_settings():
    data = request.json
    conn = get_connection()
    c = conn.cursor()
    wo_interval = data.get('work_order_interval', 0)
    rpt_interval = data.get('report_interval', 0)
    c.execute("INSERT OR REPLACE INTO system_settings (key, value, updated_at) VALUES ('mes_work_order_interval', ?, datetime('now','localtime'))", (str(wo_interval),))
    c.execute("INSERT OR REPLACE INTO system_settings (key, value, updated_at) VALUES ('mes_report_interval', ?, datetime('now','localtime'))", (str(rpt_interval),))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})

@app.route('/api/mes-sync/work-orders', methods=['POST'])
@login_required
@planner_required
def api_sync_work_orders():
    import subprocess
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT INTO sync_logs (sync_type, status) VALUES ('work_orders', 'running')")
    log_id = c.lastrowid
    conn.commit()
    conn.close()
    try:
        script = os.path.join(os.path.dirname(__file__), 'scripts', 'sync_work_orders.py')
        result = subprocess.run(
            [sys.executable, script],
            capture_output=True, text=True, timeout=300,
            cwd=os.path.dirname(__file__)
        )
        output = result.stdout.strip() if result.stdout else ''
        errors = result.stderr.strip() if result.stderr else ''
        if result.returncode == 0:
            count = 0
            for line in output.split('\n'):
                if line.startswith('IMPORTED:'):
                    count = int(line.split(':')[1])
                    break
            conn = get_connection()
            c = conn.cursor()
            c.execute("UPDATE sync_logs SET status='success', record_count=?, detail=? WHERE id=?", (count, output[-500:], log_id))
            conn.commit()
            conn.close()
            return jsonify({'ok': True, 'count': count, 'output': output[-1000:]})
        else:
            conn = get_connection()
            c = conn.cursor()
            c.execute("UPDATE sync_logs SET status='error', detail=? WHERE id=?", (errors[-500:], log_id))
            conn.commit()
            conn.close()
            return jsonify({'ok': False, 'error': errors[-500:]})
    except subprocess.TimeoutExpired:
        conn = get_connection()
        c = conn.cursor()
        c.execute("UPDATE sync_logs SET status='error', detail='同步超时(>300秒)' WHERE id=?", (log_id,))
        conn.commit()
        conn.close()
        return jsonify({'ok': False, 'error': '同步超时(>300秒)'})
    except Exception as e:
        conn = get_connection()
        c = conn.cursor()
        c.execute("UPDATE sync_logs SET status='error', detail=? WHERE id=?", (str(e)[:500], log_id))
        conn.commit()
        conn.close()
        return jsonify({'ok': False, 'error': str(e)})

@app.route('/api/mes-sync/reports', methods=['POST'])
@login_required
@planner_required
def api_sync_reports():
    import subprocess
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT INTO sync_logs (sync_type, status) VALUES ('reports', 'running')")
    log_id = c.lastrowid
    conn.commit()
    conn.close()
    try:
        script = os.path.join(os.path.dirname(__file__), 'scripts', 'sync_reports.py')
        result = subprocess.run(
            [sys.executable, script],
            capture_output=True, text=True, timeout=300,
            cwd=os.path.dirname(__file__)
        )
        output = result.stdout.strip() if result.stdout else ''
        errors = result.stderr.strip() if result.stderr else ''
        if result.returncode == 0:
            count = 0
            for line in output.split('\n'):
                if line.startswith('IMPORTED:'):
                    count = int(line.split(':')[1])
                    break
            conn = get_connection()
            c = conn.cursor()
            c.execute("UPDATE sync_logs SET status='success', record_count=?, detail=? WHERE id=?", (count, output[-500:], log_id))
            conn.commit()
            conn.close()
            return jsonify({'ok': True, 'count': count, 'output': output[-1000:]})
        else:
            conn = get_connection()
            c = conn.cursor()
            c.execute("UPDATE sync_logs SET status='error', detail=? WHERE id=?", (errors[-500:], log_id))
            conn.commit()
            conn.close()
            return jsonify({'ok': False, 'error': errors[-500:]})
    except subprocess.TimeoutExpired:
        conn = get_connection()
        c = conn.cursor()
        c.execute("UPDATE sync_logs SET status='error', detail='同步超时(>300秒)' WHERE id=?", (log_id,))
        conn.commit()
        conn.close()
        return jsonify({'ok': False, 'error': '同步超时(>300秒)'})
    except Exception as e:
        conn = get_connection()
        c = conn.cursor()
        c.execute("UPDATE sync_logs SET status='error', detail=? WHERE id=?", (str(e)[:500], log_id))
        conn.commit()
        conn.close()
        return jsonify({'ok': False, 'error': str(e)})

@app.route('/api/mes-sync/logs', methods=['GET'])
@login_required
@planner_required
def api_get_sync_logs():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT id, sync_type, status, record_count, detail, created_at FROM sync_logs ORDER BY id DESC LIMIT 50")
    rows = c.fetchall()
    conn.close()
    return jsonify([{'id':r[0],'sync_type':r[1],'status':r[2],'record_count':r[3],'detail':r[4],'created_at':r[5]} for r in rows])

# ========== Schedules Lookup API ==========
@app.route('/api/schedules')
@login_required
def api_schedules():
    q = request.args.get('q', '').strip()
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 200, type=int)
    sql = "SELECT s.*, e.equipment_name FROM schedules s LEFT JOIN equipments e ON s.equipment_id=e.id WHERE 1=1"
    params = []
    if q:
        like = "%" + q + "%"
        sql += " AND (s.product_code LIKE ? OR s.process_name LIKE ? OR s.work_order_no LIKE ?)"
        params.extend([like, like, like])
    sql += " ORDER BY s.schedule_date DESC, s.start_time"
    return jsonify(paginate_query(sql, params, page, page_size))

# ========== Standard Hours Capacity API ==========
@app.route('/api/standard-hours-capacity')
@login_required
def api_standard_hours_capacity():
    q = request.args.get('q', '').strip()
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 50, type=int)
    conn = get_connection()
    c = conn.cursor()
    
    # 过滤条件: 排除半成品入库和含清洗的工序
    exclude_filter = " AND sh.process_name != '\u534a\u6210\u54c1\u5165\u5e93' AND sh.process_name NOT LIKE '%\u6e05\u6d17%'"
    
    # Base query
    sql = "SELECT sh.* FROM standard_hours sh WHERE 1=1" + exclude_filter
    params = []
    if q:
        like = "%" + q + "%"
        sql += " AND (sh.product_code LIKE ? OR sh.product_name LIKE ? OR sh.process_name LIKE ?)"
        params.extend([like, like, like])
    sql += " ORDER BY sh.product_code, sh.process_name"
    
    # Count
    count_sql = "SELECT COUNT(*) FROM (" + sql + ")"
    c.execute(count_sql, params)
    total = c.fetchone()[0]
    
    # Paginate
    page = max(1, int(page or 1))
    page_size = min(200, max(1, int(page_size or 50)))
    offset = (page - 1) * page_size
    c.execute(sql + " LIMIT ? OFFSET ?", params + [page_size, offset])
    rows = [dict(row) for row in c.fetchall()]
    
    # Enrich each row with capacity data
    for row in rows:
        pc = row['product_code']
        pn = row['process_name']
        
        # 排班产能: from schedules
        c.execute("SELECT DISTINCT capacity_per_hour FROM schedules WHERE product_code=? AND process_name=? AND capacity_per_hour > 0", (pc, pn))
        sched_caps = [r[0] for r in c.fetchall()]
        row['schedule_capacities'] = sched_caps
        if len(sched_caps) == 1:
            row['schedule_capacity'] = sched_caps[0]
        elif len(sched_caps) > 1:
            row['schedule_capacity'] = -1
        else:
            row['schedule_capacity'] = 0
        
        # 报工产能: from work_reports
        c.execute("SELECT report_qty, report_hours, order_no, operator, equipment, start_time, end_time FROM work_reports WHERE product_code=? AND process_name=? AND report_hours > 0", (pc, pn))
        reports = c.fetchall()
        caps = []
        report_details = []
        for r in reports:
            qty, hrs, ono, op, eq, st, et = r
            if hrs > 0 and qty > 0:
                cap = round(qty / hrs, 1)
                caps.append(cap)
                report_details.append({'qty': qty, 'hours': hrs, 'capacity': cap, 'order_no': ono, 'operator': op, 'equipment': eq, 'start': st, 'end': et})
        row['report_avg'] = round(sum(caps) / len(caps), 1) if caps else 0
        row['report_max'] = max(caps) if caps else 0
        row['report_min'] = min(caps) if caps else 0
        row['report_count'] = len(caps)
    
    # 优化的进度计算: 用单条SQL统计
    progress_sql = """
        SELECT 
            COUNT(DISTINCT sh.product_code || '|' || sh.process_name) as total,
            COUNT(DISTINCT CASE WHEN s.product_code IS NOT NULL OR wr.product_code IS NOT NULL THEN sh.product_code || '|' || sh.process_name END) as completed
        FROM standard_hours sh
        LEFT JOIN (
            SELECT DISTINCT product_code, process_name 
            FROM schedules 
            WHERE capacity_per_hour > 0
        ) s ON sh.product_code = s.product_code AND sh.process_name = s.process_name
        LEFT JOIN (
            SELECT DISTINCT product_code, process_name 
            FROM work_reports 
            WHERE report_hours > 0 AND report_qty > 0
        ) wr ON sh.product_code = wr.product_code AND sh.process_name = wr.process_name
        WHERE 1=1""" + exclude_filter.replace("sh.", "sh.")
    c.execute(progress_sql)
    prog = c.fetchone()
    total_combos = prog[0] or 0
    has_cap_count = prog[1] or 0
    
    conn.close()
    total_pages = max(1, (total + page_size - 1) // page_size)
    return jsonify({
        'data': rows, 
        'total': total, 
        'page': page, 
        'page_size': page_size, 
        'total_pages': total_pages,
        'progress': {
            'total': total_combos,
            'completed': has_cap_count,
            'percent': round(has_cap_count / total_combos * 100, 1) if total_combos > 0 else 0
        }
    })

# ========== System Config API ==========
@app.route('/api/system-config')
@login_required
def api_get_config():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT key, value FROM system_config")
    config = {row[0]: row[1] for row in c.fetchall()}
    conn.close()
    return jsonify(config)

@app.route('/api/system-config', methods=['POST'])
@login_required
@planner_required
def api_save_config():
    data = request.json
    conn = get_connection()
    c = conn.cursor()
    for key, value in data.items():
        c.execute("INSERT OR REPLACE INTO system_config (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})

@app.route('/api/recalculate-efficiency', methods=['POST'])
@login_required
@planner_required
def api_recalculate_efficiency():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT value FROM system_config WHERE key='capacity_baseline'")
    row = c.fetchone()
    baseline = int(row[0]) if row else 1
    capacity_map = {}
    c.execute("SELECT DISTINCT product_code, process_name FROM standard_hours WHERE process_name != '半成品入库' AND process_name NOT LIKE '%清洗%'")
    all_combos = c.fetchall()
    for pc, pn in all_combos:
        cap = 0
        if baseline == 1:
            c.execute("SELECT DISTINCT capacity_per_hour FROM schedules WHERE product_code=? AND process_name=? AND capacity_per_hour > 0", (pc, pn))
            caps = [r[0] for r in c.fetchall()]
            cap = sum(caps) / len(caps) if caps else 0
        elif baseline == 2:
            c.execute("SELECT report_qty, report_hours FROM work_reports WHERE product_code=? AND process_name=? AND report_hours > 0 AND report_qty > 0", (pc, pn))
            reports = c.fetchall()
            if reports:
                caps = [r[0]/r[1] for r in reports if r[1] > 0]
                cap = sum(caps) / len(caps) if caps else 0
        elif baseline == 3:
            c.execute("SELECT report_qty, report_hours FROM work_reports WHERE product_code=? AND process_name=? AND report_hours > 0 AND report_qty > 0", (pc, pn))
            reports = c.fetchall()
            if reports:
                caps = [r[0]/r[1] for r in reports if r[1] > 0]
                cap = max(caps) if caps else 0
        elif baseline == 4:
            c.execute("SELECT report_qty, report_hours FROM work_reports WHERE product_code=? AND process_name=? AND report_hours > 0 AND report_qty > 0", (pc, pn))
            reports = c.fetchall()
            if reports:
                caps = [r[0]/r[1] for r in reports if r[1] > 0]
                cap = min(caps) if caps else 0
        if cap > 0:
            capacity_map[(pc, pn)] = cap
    c.execute("SELECT id, product_code, process_name, report_qty, report_hours FROM work_reports WHERE report_hours > 0 AND report_qty > 0")
    reports = c.fetchall()
    updated = 0
    for rid, pc, pn, qty, hrs in reports:
        key = (pc, pn)
        if key in capacity_map and capacity_map[key] > 0:
            efficiency = round((qty / hrs) / capacity_map[key] * 100, 1)
            c.execute("UPDATE work_reports SET efficiency=? WHERE id=?", (efficiency, rid))
            updated += 1
        else:
            c.execute("UPDATE work_reports SET efficiency=0 WHERE id=?", (rid,))
    conn.commit()
    conn.close()
    return jsonify({'ok': True, 'updated': updated, 'baseline': baseline})

# ========== Personnel Reports API ==========

def _get_personnel_map():
    """Build name -> {team_id, department, position} mapping."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT name, team_id, department, position FROM personnel")
    mapping = {row[0]: {'team_id': row[1], 'department': row[2], 'position': row[3]} for row in c.fetchall()}
    conn.close()
    return mapping

def _get_standard_capacity_map():
    """Build (product_code, process_name) -> standard_hours mapping."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT product_code, process_name, standard_hours FROM standard_hours WHERE standard_hours > 0")
    mapping = {}
    for row in c.fetchall():
        key = (row[0], row[1])
        if key not in mapping:
            mapping[key] = []
        mapping[key].append(row[2])
    conn.close()
    # Average for each combo
    return {k: sum(v)/len(v) for k, v in mapping.items()}

@app.route('/api/reports/daily')
@login_required
def api_report_daily():
    date = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    team_id = request.args.get('team_id', type=int)
    
    conn = get_connection()
    c = conn.cursor()
    personnel_map = _get_personnel_map()
    
    # Get work reports for the date - 使用效率字段的平均值(排除0)
    c.execute("""SELECT operator, SUM(report_qty), SUM(report_hours), SUM(good_qty),
        AVG(CASE WHEN efficiency > 0 THEN efficiency END) as avg_efficiency
        FROM work_reports WHERE create_time LIKE ? AND report_hours > 0
        GROUP BY operator""", (date + '%',))
    report_data = {r[0]: {'qty': r[1] or 0, 'hours': r[2] or 0, 'good_qty': r[3] or 0, 'efficiency': round(r[4] or 0, 1)} for r in c.fetchall()}
    
    # Get attendance for the date
    c.execute("SELECT name, work_hours, is_overtime, leave_type FROM attendance WHERE work_date=?", (date,))
    attend_data = {r[0]: {'hours': r[1] or 0, 'overtime': r[2], 'leave': r[3] or ''} for r in c.fetchall()}
    
    conn.close()
    
    rows = []
    for name, info in personnel_map.items():
        if team_id and info['team_id'] != team_id:
            continue
        rd = report_data.get(name, {'qty': 0, 'hours': 0, 'good_qty': 0, 'efficiency': 0})
        ad = attend_data.get(name, {'hours': 0, 'overtime': 0, 'leave': ''})
        # Include if has any data: work report OR attendance record
        has_attendance = name in attend_data
        if rd['qty'] == 0 and rd['hours'] == 0 and ad['hours'] == 0 and not has_attendance:
            continue
        
        good_rate = round(rd['good_qty'] / rd['qty'] * 100, 1) if rd['qty'] > 0 else 0
        eff = rd['efficiency']
        
        rows.append({
            'name': name,
            'department': info['department'],
            'attendance_hours': ad['hours'],
            'production_hours': rd['hours'],
            'qty': rd['qty'],
            'good_rate': good_rate,
            'efficiency': eff,
            'is_overtime': ad['overtime'],
            'leave_type': ad['leave'],
        })
    
    return jsonify({'date': date, 'data': rows})

@app.route('/api/reports/personal')
@login_required
def api_report_personal():
    name = request.args.get('name', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    if not name or not date_from or not date_to:
        return jsonify({'error': '参数不完整'}), 400
    
    conn = get_connection()
    c = conn.cursor()
    std_cap = _get_standard_capacity_map()
    
    # Get work reports
    c.execute("""SELECT create_time, SUM(report_qty), SUM(report_hours), SUM(good_qty)
        FROM work_reports WHERE operator=? AND create_time BETWEEN ? AND ? AND report_hours > 0
        GROUP BY SUBSTR(create_time, 1, 10)""",
        (name, date_from + ' 00:00:00', date_to + ' 23:59:59'))
    report_data = {}
    for r in c.fetchall():
        dt = r[0][:10]
        report_data[dt] = {'qty': r[1] or 0, 'hours': r[2] or 0, 'good_qty': r[3] or 0}
    
    # Get attendance
    c.execute("SELECT work_date, work_hours, is_overtime, leave_type FROM attendance WHERE name=? AND work_date BETWEEN ? AND ?",
              (name, date_from, date_to))
    attend_data = {}
    for r in c.fetchall():
        attend_data[r[0]] = {'hours': r[1] or 0, 'overtime': r[2], 'leave': r[3] or ''}
    
    conn.close()
    
    # Build date columns
    days = []
    current = datetime.strptime(date_from, '%Y-%m-%d').date()
    end = datetime.strptime(date_to, '%Y-%m-%d').date()
    while current <= end:
        ds = current.strftime('%Y-%m-%d')
        rd = report_data.get(ds, {'qty': 0, 'hours': 0, 'good_qty': 0})
        ad = attend_data.get(ds, {'hours': 0, 'overtime': 0, 'leave': ''})
        good_rate = round(rd['good_qty'] / rd['qty'] * 100, 1) if rd['qty'] > 0 else 0
        eff = 0
        if rd['hours'] > 0:
            caps = list(std_cap.values())
            avg_cap = sum(caps) / len(caps) if caps else 0
            if avg_cap > 0:
                eff = round((rd['qty'] / rd['hours']) / avg_cap * 100, 1)
        days.append({
            'date': ds,
            'qty': rd['qty'],
            'hours': rd['hours'],
            'good_rate': good_rate,
            'efficiency': eff,
            'attendance_hours': ad['hours'],
            'is_overtime': ad['overtime'],
            'leave_type': ad['leave'],
        })
        current += timedelta(days=1)
    
    return jsonify({'name': name, 'days': days})

@app.route('/api/reports/weekly')
@login_required
def api_report_weekly():
    week_start = request.args.get('week_start', '')
    team_id = request.args.get('team_id', type=int)
    if not week_start:
        today = datetime.now().date()
        week_start = (today - timedelta(days=today.weekday())).strftime('%Y-%m-%d')
    week_end = (datetime.strptime(week_start, '%Y-%m-%d').date() + timedelta(days=6)).strftime('%Y-%m-%d')
    
    conn = get_connection()
    c = conn.cursor()
    personnel_map = _get_personnel_map()
    std_cap = _get_standard_capacity_map()
    
    # Work reports for the week - 使用效率字段
    c.execute("""SELECT operator, SUM(report_qty), SUM(report_hours), SUM(good_qty), COUNT(DISTINCT SUBSTR(create_time,1,10)),
        AVG(CASE WHEN efficiency > 0 THEN efficiency END) as avg_efficiency
        FROM work_reports WHERE create_time BETWEEN ? AND ? AND report_hours > 0
        GROUP BY operator""", (week_start + ' 00:00:00', week_end + ' 23:59:59'))
    report_data = {}
    for r in c.fetchall():
        report_data[r[0]] = {'qty': r[1] or 0, 'hours': r[2] or 0, 'good_qty': r[3] or 0, 'days': r[4] or 0, 'efficiency': round(r[5] or 0, 1)}
    
    # Attendance for the week
    c.execute("SELECT name, SUM(work_hours), SUM(is_overtime), COUNT(*) FROM attendance WHERE work_date BETWEEN ? AND ? GROUP BY name",
              (week_start, week_end))
    attend_data = {}
    for r in c.fetchall():
        attend_data[r[0]] = {'total_hours': r[1] or 0, 'overtime_days': r[2] or 0, 'work_days': r[3] or 0}
    
    conn.close()
    
    rows = []
    for name, info in personnel_map.items():
        if team_id and info['team_id'] != team_id:
            continue
        rd = report_data.get(name, {'qty': 0, 'hours': 0, 'good_qty': 0, 'days': 0})
        ad = attend_data.get(name, {'total_hours': 0, 'overtime_days': 0, 'work_days': 0})
        if rd['qty'] == 0 and rd['hours'] == 0 and ad['total_hours'] == 0:
            continue
        
        good_rate = round(rd['good_qty'] / rd['qty'] * 100, 1) if rd['qty'] > 0 else 0
        eff = rd.get('efficiency', 0)
        util_rate = round(rd['hours'] / ad['total_hours'] * 100, 1) if ad['total_hours'] > 0 else 0
        daily_avg = round(rd['qty'] / rd['days'], 1) if rd['days'] > 0 else 0
        
        rows.append({
            'name': name, 'department': info['department'],
            'work_days': ad['work_days'],
            'total_attendance_hours': ad['total_hours'],
            'total_production_hours': rd['hours'],
            'total_qty': rd['qty'],
            'good_rate': good_rate,
            'avg_efficiency': eff,
            'overtime_days': ad['overtime_days'],
            'utilization_rate': util_rate,
            'daily_avg_qty': daily_avg,
        })
    
    return jsonify({'week_start': week_start, 'week_end': week_end, 'data': rows})

@app.route('/api/reports/monthly')
@login_required
def api_report_monthly():
    month = request.args.get('month', datetime.now().strftime('%Y-%m'))
    team_id = request.args.get('team_id', type=int)
    date_from = month + '-01'
    import calendar
    y, m = map(int, month.split('-'))
    last_day = calendar.monthrange(y, m)[1]
    date_to = f"{month}-{last_day:02d}"
    
    conn = get_connection()
    c = conn.cursor()
    personnel_map = _get_personnel_map()
    std_cap = _get_standard_capacity_map()
    
    # Work reports - 使用效率字段
    c.execute("""SELECT operator, SUM(report_qty), SUM(report_hours), SUM(good_qty), COUNT(DISTINCT SUBSTR(create_time,1,10)),
        AVG(CASE WHEN efficiency > 0 THEN efficiency END) as avg_efficiency
        FROM work_reports WHERE create_time BETWEEN ? AND ? AND report_hours > 0
        GROUP BY operator""", (date_from + ' 00:00:00', date_to + ' 23:59:59'))
    report_data = {}
    for r in c.fetchall():
        report_data[r[0]] = {'qty': r[1] or 0, 'hours': r[2] or 0, 'good_qty': r[3] or 0, 'days': r[4] or 0, 'efficiency': round(r[5] or 0, 1)}
    
    # Attendance
    c.execute("SELECT name, SUM(work_hours), SUM(is_overtime), COUNT(*), SUM(CASE WHEN leave_type != '' AND leave_type IS NOT NULL THEN 1 ELSE 0 END) FROM attendance WHERE work_date BETWEEN ? AND ? GROUP BY name",
              (date_from, date_to))
    attend_data = {}
    for r in c.fetchall():
        attend_data[r[0]] = {'total_hours': r[1] or 0, 'overtime_days': r[2] or 0, 'work_days': r[3] or 0, 'leave_days': r[4] or 0}
    
    # Planned qty from schedules
    c.execute("SELECT team_id, SUM(quantity) FROM schedules WHERE schedule_date BETWEEN ? AND ? GROUP BY team_id",
              (date_from, date_to))
    planned_by_team = {r[0]: r[1] for r in c.fetchall()}
    
    conn.close()
    
    rows = []
    for name, info in personnel_map.items():
        if team_id and info['team_id'] != team_id:
            continue
        rd = report_data.get(name, {'qty': 0, 'hours': 0, 'good_qty': 0, 'days': 0})
        ad = attend_data.get(name, {'total_hours': 0, 'overtime_days': 0, 'work_days': 0, 'leave_days': 0})
        if rd['qty'] == 0 and rd['hours'] == 0 and ad['total_hours'] == 0:
            continue
        
        good_rate = round(rd['good_qty'] / rd['qty'] * 100, 1) if rd['qty'] > 0 else 0
        eff = rd.get('efficiency', 0)
        util_rate = round(rd['hours'] / ad['total_hours'] * 100, 1) if ad['total_hours'] > 0 else 0
        daily_avg = round(rd['qty'] / rd['days'], 1) if rd['days'] > 0 else 0
        planned = planned_by_team.get(info['team_id'], 0)
        achieve_rate = round(rd['qty'] / planned * 100, 1) if planned > 0 else 0
        
        rows.append({
            'name': name, 'department': info['department'],
            'work_days': ad['work_days'],
            'total_attendance_hours': ad['total_hours'],
            'total_production_hours': rd['hours'],
            'total_qty': rd['qty'],
            'good_rate': good_rate,
            'avg_efficiency': eff,
            'overtime_days': ad['overtime_days'],
            'utilization_rate': util_rate,
            'daily_avg_qty': daily_avg,
            'achieve_rate': achieve_rate,
            'leave_days': ad['leave_days'],
        })
    
    return jsonify({'month': month, 'data': rows})

@app.route('/api/attendance/sync', methods=['POST'])
@login_required
@planner_required
def api_attendance_sync():
    data = request.json
    date_from = data.get('date_from', '')
    date_to = data.get('date_to', '')
    if not date_from or not date_to:
        return jsonify({'error': '请选择日期范围'}), 400
    try:
        from utils.attendance_api import sync_attendance
        count = sync_attendance(date_from, date_to)
        return jsonify({'ok': True, 'count': count})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/api/attendance/test', methods=['POST'])
@login_required
@planner_required
def api_attendance_test():
    try:
        from utils.attendance_api import fetch_attendance
        from datetime import datetime, timedelta
        test_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        records = fetch_attendance(test_date)
        if records is not None:
            return jsonify({'ok': True, 'count': len(records), 'date': test_date})
        else:
            return jsonify({'ok': False, 'error': '无法获取考勤数据，请检查API地址和Key'})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})

@app.route('/api/attendance', methods=['GET'])
@login_required
def api_attendance():
    name = request.args.get('name', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    conn = get_connection()
    c = conn.cursor()
    sql = "SELECT * FROM attendance WHERE 1=1"
    params = []
    if name:
        sql += " AND name=?"
        params.append(name)
    if date_from:
        sql += " AND work_date>=?"
        params.append(date_from)
    if date_to:
        sql += " AND work_date<=?"
        params.append(date_to)
    sql += " ORDER BY work_date DESC LIMIT 100"
    c.execute(sql, params)
    r = [dict(row) for row in c.fetchall()]
    conn.close()
    return jsonify(r)


# ========== Attendance Settings API ==========
@app.route('/api/attendance/settings', methods=['GET'])
@login_required
def api_attendance_settings_get():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT key, value FROM system_settings WHERE key LIKE 'attendance_%'")
    config = {row[0]: row[1] for row in c.fetchall()}
    conn.close()
    return jsonify({
        'api_url': config.get('attendance_api_url', 'http://10.6.201.10:7777/ddkq/api/third-party/attendance'),
        'api_key': config.get('attendance_api_key', 'tk_cs_20260601'),
        'auto_sync': config.get('attendance_auto_sync', '0'),
    })

@app.route('/api/attendance/settings', methods=['POST'])
@login_required
@planner_required
def api_attendance_settings_save():
    data = request.json
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO system_settings (key, value, updated_at) VALUES ('attendance_api_url', ?, datetime('now'))", (data.get('api_url', ''),))
    c.execute("INSERT OR REPLACE INTO system_settings (key, value, updated_at) VALUES ('attendance_api_key', ?, datetime('now'))", (data.get('api_key', ''),))
    c.execute("INSERT OR REPLACE INTO system_settings (key, value, updated_at) VALUES ('attendance_auto_sync', ?, datetime('now'))", (str(data.get('auto_sync', '0')),))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})

# ========== Export API ==========
@app.route('/api/export/<data_type>')
@login_required
def api_export(data_type):
    import io
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    conn = get_connection()
    c = conn.cursor()
    if data_type == 'process_routes':
        ws.title = '工艺路线'
        c.execute("SELECT route_code, route_name, product_code, process_list, remark FROM process_routes ORDER BY route_code")
        ws.append(['工艺路线编号', '路线名称', '产品编码', '工序列表', '备注'])
    elif data_type == 'cycles':
        ws.title = '生产周期'
        c.execute("SELECT product_code, production_days, lead_days FROM production_cycles ORDER BY product_code")
        ws.append(['产品编码', '生产周期(天)', '提前时间(天)'])
    elif data_type == 'bom':
        ws.title = '物料清单'
        c.execute("SELECT parent_product_code, parent_product_name, child_product_code, child_product_name, quantity, unit, process_team FROM bom ORDER BY parent_product_code")
        ws.append(['父件编码', '父件名称', '子件编码', '子件名称', '用量', '单位', '生产班组'])
    elif data_type == 'work_orders':
        ws.title = '工单数据'
        c.execute("SELECT order_no, product_code, product_name, quantity, completed_qty, due_date, priority, status, process_progress, source FROM work_orders ORDER BY order_no")
        ws.append(['工单编号', '产品编码', '产品名称', '计划数量', '完成数量', '交期', '优先级', '状态', '工序进度', '来源'])
    else:
        return jsonify({'error': 'unsupported'}), 400
    for row in c.fetchall():
        ws.append(list(row))
    conn.close()
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    from flask import send_file
    return send_file(buf, as_attachment=True, download_name=data_type + '_export.xlsx',
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

# ========== User Management API ==========
@app.route('/api/users')
@login_required
@planner_required
def api_users():
    return jsonify(get_all_users())

@app.route('/api/users', methods=['POST'])
@login_required
@planner_required
def api_user_create():
    data = request.json
    uid = create_user(data['username'], data['password'], data['display_name'],
                      data.get('role', 'team'), data.get('team_id'))
    if uid:
        return jsonify({'id': uid, 'ok': True})
    return jsonify({'error': '用户名已存在'}), 400

@app.route('/api/users/<int:uid>', methods=['PUT'])
@login_required
@planner_required
def api_user_update(uid):
    data = request.json
    update_user(uid, data['display_name'], data.get('role', 'team'),
                data.get('team_id'), data.get('is_active', 1))
    return jsonify({'ok': True})

@app.route('/api/users/<int:uid>', methods=['DELETE'])
@login_required
@planner_required
def api_user_delete(uid):
    delete_user(uid)
    return jsonify({'ok': True})

@app.route('/api/users/<int:uid>/reset-password', methods=['POST'])
@login_required
@planner_required
def api_user_reset_pwd(uid):
    data = request.json
    reset_password(uid, data.get('new_password', '123456'))
    return jsonify({'ok': True})

# ========== Shipping Plan API ==========
@app.route('/api/shipping-plan')
@login_required
def api_shipping_plan():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM shipping_plan ORDER BY ship_date LIMIT 200")
    r = [dict(row) for row in c.fetchall()]
    conn.close()
    return jsonify(r)

# ========== Statistics API ==========
@app.route('/api/statistics')
@login_required
def api_statistics():
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    if not date_from:
        date_from = (datetime.now() - timedelta(days=6)).strftime('%Y-%m-%d')
    if not date_to:
        date_to = datetime.now().strftime('%Y-%m-%d')
    conn = get_connection()
    c = conn.cursor()

    # 1. Load all teams
    c.execute("SELECT id, name FROM teams ORDER BY id")
    teams = [dict(row) for row in c.fetchall()]

    # 2. Load all process->team mapping once
    c.execute("SELECT process_name, team_name FROM processes WHERE team_name IS NOT NULL AND team_name != '' AND team_name != '报工权限'")
    proc_team_map = {}
    for r in c.fetchall():
        proc_team_map[r[0]] = r[1]

    # 3. Bulk load schedules for date range
    c.execute("SELECT team_id, schedule_date, product_code, process_name, quantity, capacity_per_hour FROM schedules WHERE schedule_date BETWEEN ? AND ?", (date_from, date_to))
    all_schedules = c.fetchall()

    # 4. Bulk load work_reports for date range
    c.execute("SELECT product_code, process_name, report_qty, report_hours, create_time FROM work_reports WHERE create_time BETWEEN ? AND ?",
              (date_from + ' 00:00:00', date_to + ' 23:59:59'))
    all_reports = c.fetchall()
    conn.close()

    # 5. Build schedule index: (team_id, date) -> total_qty
    sched_by_team_date = {}
    # Build schedule capacity index: (product_code, process_name, date) -> capacity
    sched_capacity = {}
    for s in all_schedules:
        tid, dt, pc, pn, qty, cap = s[0], s[1], s[2], s[3], s[4] or 0, s[5] or 0
        key = (tid, dt)
        sched_by_team_date[key] = sched_by_team_date.get(key, 0) + qty
        if cap > 0:
            sched_capacity[(pc, pn, dt)] = cap

    # 6. Build report index: (product_code, process_name, date) -> {qty, hours}
    report_by_key = {}
    for r in all_reports:
        pc, pn, qty, hrs, ct = r[0], r[1], r[2] or 0, r[3] or 0, r[4] or ''
        dt = ct[:10] if ct else ''
        key = (pc, pn, dt)
        if key not in report_by_key:
            report_by_key[key] = {'qty': 0, 'hours': 0}
        report_by_key[key]['qty'] += qty
        report_by_key[key]['hours'] += hrs

    # 7. Build team->process set
    team_procs = {}
    for pn, tn in proc_team_map.items():
        for team in teams:
            if team['name'] in tn:
                team_procs.setdefault(team['id'], set()).add(pn)

    # 8. Generate result
    result = {}
    for team in teams:
        tid = team['id']
        tname = team['name']
        procs = team_procs.get(tid, set())
        days = []
        current = datetime.strptime(date_from, '%Y-%m-%d').date()
        end = datetime.strptime(date_to, '%Y-%m-%d').date()
        while current <= end:
            ds = current.strftime('%Y-%m-%d')
            planned = sched_by_team_date.get((tid, ds), 0)
            # Sum completed qty for this team's processes on this date
            completed = 0
            efficiencies = []
            for (pc, pn, dt), data in report_by_key.items():
                if dt == ds and pn in procs:
                    completed += data['qty']
                    if data['hours'] > 0:
                        cap = sched_capacity.get((pc, pn, ds), 0)
                        if cap > 0:
                            eff = round((data['qty'] / data['hours']) / cap * 100, 1)
                            efficiencies.append(eff)
            rate = round(completed / planned * 100, 1) if planned > 0 else 0
            eff_avg = round(sum(efficiencies) / len(efficiencies), 1) if efficiencies else 0
            days.append({'date': ds, 'planned_qty': planned, 'completed_qty': completed, 'completion_rate': rate, 'efficiency': eff_avg})
            current += timedelta(days=1)
        result[tid] = {'team_name': tname, 'days': days}

    return jsonify(result)

if __name__ == "__main__":
    init_database()
    app.run(debug=True, host="0.0.0.0", port=5000)


