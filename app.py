# -*- coding: utf-8 -*-
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import os
import sys
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

def planner_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get('role') != 'planner':
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
def alerts_page():
    return render_template('alerts.html')

@app.route('/schedule-page')
@login_required
def schedule_page():
    return render_template('schedule.html')

@app.route('/orders-page')
@login_required
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

@app.route('/statistics-page')
@login_required
def statistics_page():
    return render_template('statistics.html')

@app.route('/import-page')
@login_required
def import_page():
    return render_template('import.html')

@app.route('/admin/users')
@login_required
def admin_users_page():
    return render_template('admin_users.html')

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
    return jsonify(get_all_equipments(team_id, q))

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
    conn = get_connection()
    c = conn.cursor()
    status = request.args.get('status')
    keyword = request.args.get('q', '')
    if status:
        c.execute("SELECT * FROM work_orders WHERE status=? ORDER BY due_date", (status,))
    elif keyword:
        c.execute("SELECT * FROM work_orders WHERE order_no LIKE ? OR product_code LIKE ? OR product_name LIKE ? ORDER BY due_date",
                  ('%' + keyword + '%', '%' + keyword + '%', '%' + keyword + '%'))
    else:
        c.execute("SELECT * FROM work_orders ORDER BY due_date")
    r = [dict(row) for row in c.fetchall()]
    conn.close()
    return jsonify(r)

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
    conn = get_connection()
    c = conn.cursor()
    q = request.args.get('q', '')
    team = request.args.get('team', '')
    sql = "SELECT * FROM processes WHERE 1=1"
    params = []
    if q:
        sql += " AND (process_name LIKE ? OR process_code LIKE ?)"
        params.extend(['%'+q+'%', '%'+q+'%'])
    if team:
        # Support comma-separated team names
        sql += " AND team_name LIKE ?"
        params.append('%' + team + '%')
    sql += " ORDER BY team_name, process_code"
    c.execute(sql, params)
    r = [dict(row) for row in c.fetchall()]
    conn.close()
    return jsonify(r)

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

# ========== Process Routes CRUD ==========
@app.route('/api/process-routes')
@login_required
def api_process_routes():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM process_routes ORDER BY route_code")
    r = [dict(row) for row in c.fetchall()]
    conn.close()
    return jsonify(r)

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
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM bom ORDER BY parent_product_code")
    r = [dict(row) for row in c.fetchall()]
    conn.close()
    return jsonify(r)

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
    conn = get_connection()
    c = conn.cursor()
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
    c.execute(sql, params)
    r = [dict(row) for row in c.fetchall()]
    conn.close()
    return jsonify(r)

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
    conn = get_connection()
    c = conn.cursor()
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
    c.execute(sql, params)
    r = [dict(row) for row in c.fetchall()]
    conn.close()
    return jsonify(r)

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
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT s.team_id, t.name as team_name, SUM(s.quantity) as planned_qty, SUM(CASE WHEN s.task_status='completed' THEN s.quantity ELSE 0 END) as completed_qty, COUNT(*) as task_count FROM schedules s LEFT JOIN teams t ON s.team_id = t.id GROUP BY s.team_id")
    stats = [dict(row) for row in c.fetchall()]
    conn.close()
    return jsonify(stats)

@app.route('/api/statistics/daily')
@login_required
def api_statistics_daily():
    conn = get_connection()
    c = conn.cursor()
    today = datetime.now().date()
    days = []
    for i in range(6, -1, -1):
        d = (today - timedelta(days=i)).strftime('%Y-%m-%d')
        c.execute("SELECT COALESCE(SUM(quantity),0), COALESCE(SUM(CASE WHEN task_status='completed' THEN quantity ELSE 0 END),0) FROM schedules WHERE schedule_date=?", (d,))
        row = c.fetchone()
        days.append({'date': d, 'planned': row[0], 'completed': row[1]})
    conn.close()
    return jsonify(days)

if __name__ == "__main__":
    init_database()
    app.run(debug=True, host="0.0.0.0", port=5000)
