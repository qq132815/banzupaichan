# -*- coding: utf-8 -*-
import os
import sys
import openpyxl

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

from utils.db import get_connection

conn = get_connection()
c = conn.cursor()

# ===== Create process-equipment mapping =====
print('Creating process-equipment mapping...')
c.execute('DELETE FROM process_equipment')

# Get team name to id mapping
c.execute('SELECT id, name FROM teams')
teams = {row[1]: row[0] for row in c.fetchall()}
print('Teams:', teams)

# Get all equipment
c.execute('SELECT id, equipment_code, equipment_name, team_id FROM equipments')
all_equipment = c.fetchall()

# Get team_id to team_name mapping
team_id_to_name = {v: k for k, v in teams.items()}

# Get all processes
c.execute('SELECT id, process_code, process_name, team_name FROM processes')
all_processes = c.fetchall()

mapped = 0
for proc in all_processes:
    proc_id = proc[0]
    proc_code = proc[1]
    proc_name = proc[2]
    proc_team = proc[3]  # e.g.,  前段 or 前段,扣压
    
    if not proc_team:
        continue
    
    # Split team names (some processes belong to multiple teams)
    proc_team_list = [t.strip() for t in proc_team.split(',')]
    
    # Find equipment for matching teams
    for eq in all_equipment:
        eq_id = eq[0]
        eq_team_id = eq[2]
        eq_team_name = team_id_to_name.get(eq_team_id, '')
        
        # Check if this equipment's team is in the process's team list
        for p_team in proc_team_list:
            if p_team == eq_team_name:
                c.execute('INSERT OR IGNORE INTO process_equipment (process_code, equipment_id, is_primary) VALUES (?, ?, ?)',
                         (proc_code, eq_id, 1))
                mapped += 1
                break

print(f'Created {mapped} process-equipment mappings')

# ===== Update app.py with new API endpoints =====
print('Updating app.py...')

app_path = os.path.join(BASE, 'app.py')
with open(app_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Add new API endpoints
new_apis = []

# Get processes for a product (from process routes)
new_apis.append('')
new_apis.append('@app.route(\'/api/product-processes\')')
new_apis.append('def api_product_processes():')
new_apis.append('    product_code = request.args.get(\'product_code\', \'\')')
new_apis.append('    conn = get_connection()')
new_apis.append('    c = conn.cursor()')
new_apis.append('    # Search process routes for this product')
new_apis.append('    c.execute(SELECT route_code route_name process_list FROM process_routes WHERE product_code LIKE ?, (\'%\' + product_code + \'%\',))')
new_apis.append('    routes = c.fetchall()')
new_apis.append('    result = []')
new_apis.append('    for r in routes:')
new_apis.append('        route_code = r[0]')
new_apis.append('        route_name = r[1]')
new_apis.append('        process_list = r[2]')
new_apis.append('        if process_list:')
new_apis.append('            for proc_name in process_list.split(\',\'):')
new_apis.append('                proc_name = proc_name.strip()')
new_apis.append('                # Find process code by name')
new_apis.append('                c.execute(SELECT process_code team_name FROM processes WHERE process_name=?, (proc_name,))')
new_apis.append('                proc = c.fetchone()')
new_apis.append('                if proc:')
new_apis.append('                    result.append({')
new_apis.append('                        \'route_code\': route_code,')
new_apis.append('                        \'process_code\': proc[0],')
new_apis.append('                        \'process_name\': proc_name,')
new_apis.append('                        \'team_name\': proc[1]')
new_apis.append('                    })')
new_apis.append('    conn.close()')
new_apis.append('    return jsonify(result)')

# Get equipment for a process
new_apis.append('')
new_apis.append('@app.route(\'/api/process-equipment\')')
new_apis.append('def api_process_equipment():')
new_apis.append('    process_code = request.args.get(\'process_code\', \'\')')
new_apis.append('    conn = get_connection()')
new_apis.append('    c = conn.cursor()')
new_apis.append('    c.execute(SELECT e.id e.equipment_code e.equipment_name e.equipment_type e.capacity_per_hour e.location FROM equipments e JOIN process_equipment pe ON e.id = pe.equipment_id WHERE pe.process_code = ?, (process_code,))')
new_apis.append('    equips = [dict(zip([\'id\', \'equipment_code\', \'equipment_name\', \'equipment_type\', \'capacity_per_hour\', \'location\'], row)) for row in c.fetchall()]')
new_apis.append('    conn.close()')
new_apis.append('    return jsonify(equips)')

# Search orders
new_apis.append('')
new_apis.append('@app.route(\'/api/search-orders\')')
new_apis.append('def api_search_orders():')
new_apis.append('    keyword = request.args.get(\'q\', \'\')')
new_apis.append('    conn = get_connection()')
new_apis.append('    c = conn.cursor()')
new_apis.append('    c.execute(SELECT * FROM work_orders WHERE product_code LIKE ? OR order_no LIKE ? LIMIT 20, (\'%\' + keyword + \'%\', \'%\' + keyword + \'%\'))')
new_apis.append('    orders = [dict(row) for row in c.fetchall()]')
new_apis.append('    conn.close()')
new_apis.append('    return jsonify(orders)')

# Insert before 'if __name__'
insert_point = content.find('if __name__')
if insert_point > 0:
    new_content = content[:insert_point] + chr(10).join(new_apis) + chr(10) + content[insert_point:]
    with open(app_path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    print('Added new API endpoints to app.py')
else:
    print('Could not find insertion point in app.py')

# ===== Create new schedule page =====
print('Creating new schedule page...')

# ... will add template creation here

conn.commit()
conn.close()
print('Rebuild2 complete!')