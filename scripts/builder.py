# -*- coding: utf-8 -*-
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
p = chr(40)
q = chr(41)
star = chr(42)
dist = chr(68)+chr(73)+chr(83)+chr(84)+chr(73)+chr(78)+chr(67)+chr(84)

def w(rel, content):
    fp = os.path.join(BASE, rel)
    os.makedirs(os.path.dirname(fp), exist_ok=True)
    with open(fp, 'w', encoding='utf-8') as f:
        f.write(content)
    print('Created: ' + rel)

# db.py
db_lines = []
db_lines.append('# -*- coding: utf-8 -*-')
db_lines.append('import sqlite3')
db_lines.append('import os')
db_lines.append('from datetime import datetime')
db_lines.append('')
db_lines.append('DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), ' + chr(34) + 'data' + chr(34) + ', ' + chr(34) + 'production.db' + chr(34) + ')')
db_lines.append('')
db_lines.append('def get_connection():')
db_lines.append('    conn = sqlite3.connect(DB_PATH)')
db_lines.append('    conn.row_factory = sqlite3.Row')
db_lines.append('    return conn')
db_lines.append('')
db_lines.append('def init_database():')
db_lines.append('    conn = get_connection()')
db_lines.append('    c = conn.cursor()')

tables = {
    'teams': 'id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, leader TEXT, members TEXT, shift_type TEXT, shift_start TEXT, shift_end TEXT',
    'equipments': 'id INTEGER PRIMARY KEY AUTOINCREMENT, equipment_code TEXT NOT NULL UNIQUE, equipment_name TEXT NOT NULL, team_id INTEGER, equipment_type TEXT, status TEXT, capacity_per_hour REAL, location TEXT',
    'products': 'id INTEGER PRIMARY KEY AUTOINCREMENT, product_code TEXT NOT NULL UNIQUE, product_name TEXT, product_type TEXT, safety_stock REAL, unit TEXT',
    'work_orders': 'id INTEGER PRIMARY KEY AUTOINCREMENT, order_no TEXT, product_code TEXT, product_name TEXT, quantity REAL, completed_qty REAL, due_date TEXT, priority TEXT, status TEXT, source TEXT, parent_order_no TEXT',
    'process_routes': 'id INTEGER PRIMARY KEY AUTOINCREMENT, route_code TEXT, route_name TEXT, product_code TEXT, process_list TEXT, remark TEXT',
    'processes': 'id INTEGER PRIMARY KEY AUTOINCREMENT, process_code TEXT NOT NULL UNIQUE, process_name TEXT, team_name TEXT',
    'schedules': 'id INTEGER PRIMARY KEY AUTOINCREMENT, equipment_id INTEGER, work_order_no TEXT, process_code TEXT, process_name TEXT, schedule_date TEXT, start_time TEXT, end_time TEXT, quantity REAL, hours REAL, capacity_per_hour REAL, is_overtime INTEGER, team_id INTEGER, task_status TEXT, priority TEXT',
    'reports': 'id INTEGER PRIMARY KEY AUTOINCREMENT, work_order_no TEXT, process_code TEXT, equipment_id INTEGER, team_id INTEGER, report_date TEXT, planned_qty REAL, actual_qty REAL, operator TEXT',
    'shipping_plan': 'id INTEGER PRIMARY KEY AUTOINCREMENT, product_code TEXT NOT NULL, quantity REAL, ship_date TEXT, k3_order_no TEXT',
    'production_cycles': 'id INTEGER PRIMARY KEY AUTOINCREMENT, product_code TEXT NOT NULL, production_days REAL, lead_days REAL',
    'bom': 'id INTEGER PRIMARY KEY AUTOINCREMENT, parent_product_code TEXT, parent_product_name TEXT, child_product_code TEXT, child_product_name TEXT, quantity REAL, unit TEXT, process_team TEXT',
    'alerts': 'id INTEGER PRIMARY KEY AUTOINCREMENT, product_code TEXT, order_no TEXT, alert_level TEXT, due_date TEXT, quantity REAL, scheduled_qty REAL, shortage_qty REAL, days_remaining INTEGER, message TEXT, status TEXT',
}
for name, cols in tables.items():
    sql = 'CREATE TABLE IF NOT EXISTS ' + name + ' ' + p + cols + q
    db_lines.append('    c.execute(' + chr(34) + sql + chr(34) + ')')

idx1 = 'CREATE INDEX IF NOT EXISTS idx_sp_date ON shipping_plan'
db_lines.append('    c.execute(' + chr(34) + idx1 + chr(34) + ' + p + ' + chr(34) + 'ship_date' + chr(34) + ' + q')
idx2 = 'CREATE INDEX IF NOT EXISTS idx_alert_lvl ON alerts'
db_lines.append('    c.execute(' + chr(34) + idx2 + chr(34) + ' + p + ' + chr(34) + 'alert_level' + chr(34) + ' + q')

db_lines.append('    conn.commit()')
db_lines.append('    conn.close()')
db_lines.append('    print(' + chr(34) + 'Database initialized' + chr(34) + ')')
db_lines.append('')
db_lines.append('def get_all_teams():')
db_lines.append('    conn = get_connection()')
db_lines.append('    c = conn.cursor()')
db_lines.append('    c.execute(' + chr(34) + 'SELECT * FROM teams ORDER BY id' + chr(34) + ')')
db_lines.append('    r = [dict(row) for row in c.fetchall()]')
db_lines.append('    conn.close()')
db_lines.append('    return r')
db_lines.append('')
db_lines.append('def get_all_equipments(team_id=None):')
db_lines.append('    conn = get_connection()')
db_lines.append('    c = conn.cursor()')
db_lines.append('    if team_id:')
db_lines.append('        c.execute(' + chr(34) + 'SELECT * FROM equipments WHERE team_id=?' + chr(34) + ', (team_id,))')
db_lines.append('    else:')
db_lines.append('        c.execute(' + chr(34) + 'SELECT * FROM equipments ORDER BY team_id, equipment_code' + chr(34) + ')')
db_lines.append('    r = [dict(row) for row in c.fetchall()]')
db_lines.append('    conn.close()')
db_lines.append('    return r')
db_lines.append('')
db_lines.append('def get_alerts(level=None, limit=50):')
db_lines.append('    conn = get_connection()')
db_lines.append('    c = conn.cursor()')
db_lines.append('    if level:')
db_lines.append('        c.execute(' + chr(34) + 'SELECT * FROM alerts WHERE alert_level=? AND status=? ORDER BY due_date LIMIT ?' + chr(34) + ', (level, ' + chr(34) + 'active' + chr(34) + ', limit))')
db_lines.append('    else:')
db_lines.append('        c.execute(' + chr(34) + 'SELECT * FROM alerts WHERE status=? ORDER BY due_date LIMIT ?' + chr(34) + ', (' + chr(34) + 'active' + chr(34) + ', limit))')
db_lines.append('    r = [dict(row) for row in c.fetchall()]')
db_lines.append('    conn.close()')
db_lines.append('    return r')
db_lines.append('')
db_lines.append('def get_dashboard_stats():')
db_lines.append('    conn = get_connection()')
db_lines.append('    c = conn.cursor()')
db_lines.append('    stats = {}')
db_lines.append('    c.execute(' + chr(34) + 'SELECT COUNT(' + star + ') FROM alerts WHERE alert_level=? AND status=?' + chr(34) + ', (' + chr(34) + 'red' + chr(34) + ', ' + chr(34) + 'active' + chr(34) + '))')
db_lines.append('    stats[' + chr(34) + 'red_alerts' + chr(34) + '] = c.fetchone()[0]')
db_lines.append('    today = datetime.now().strftime(' + chr(34) + '%Y-%m-%d' + chr(34) + ')')
db_lines.append('    c.execute(' + chr(34) + 'SELECT COUNT(' + star + ') FROM schedules WHERE schedule_date=?' + chr(34) + ', (today,))')
db_lines.append('    stats[' + chr(34) + 'today_schedules' + chr(34) + '] = c.fetchone()[0]')
db_lines.append('    c.execute(' + chr(34) + 'SELECT COUNT(' + dist + ' order_no) FROM work_orders WHERE status=?' + chr(34) + ', (' + chr(34) + 'in_progress' + chr(34) + ',))')
db_lines.append('    stats[' + chr(34) + 'in_progress_orders' + chr(34) + '] = c.fetchone()[0]')
db_lines.append('    c.execute(' + chr(34) + 'SELECT COUNT(' + star + ') FROM alerts WHERE status=?' + chr(34) + ', (' + chr(34) + 'active' + chr(34) + ',))')
db_lines.append('    stats[' + chr(34) + 'total_alerts' + chr(34) + '] = c.fetchone()[0]')
db_lines.append('    conn.close()')
db_lines.append('    return stats')
db_lines.append('')
db_lines.append('if __name__ == ' + chr(34) + '__main__' + chr(34) + ':')
db_lines.append('    init_database()')

w('utils/db.py', chr(10).join(db_lines))
print('All done!')