# -*- coding: utf-8 -*-
import sqlite3, os

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'production.db')
conn = sqlite3.connect(DB)
c = conn.cursor()

# Get all process names from routes
c.execute('SELECT process_list FROM process_routes')
all_procs = set()
for r in c.fetchall():
    if r[0]:
        for p in r[0].split(','):
            p = p.strip()
            if p:
                all_procs.add(p)

# Get existing process names
c.execute('SELECT process_name FROM processes')
existing = set(r[0] for r in c.fetchall())

# Find missing
missing = all_procs - existing
print(f'Total unique process names in routes: {len(all_procs)}')
print(f'Existing in processes table: {len(existing)}')
print(f'Missing: {len(missing)}')

# Assign missing processes to teams based on route context
# We need to figure out which team each process belongs to
# Read routes with their team context
c.execute('SELECT route_code, process_list FROM process_routes')
team_assign = {}
for r in c.fetchall():
    route_code = r[0] or ''
    proc_list = r[1] or ''
    # Determine team from route_code
    if '前段' in route_code:
        team = '前段'
    elif '焊接' in route_code:
        team = '焊接'
    elif '扣压' in route_code:
        team = '扣压'
    elif '装配' in route_code:
        team = '装配包装'
    else:
        team = '前段'  # default
    for p in proc_list.split(','):
        p = p.strip()
        if p and p not in team_assign:
            team_assign[p] = team

# Insert missing processes
import random
code_counter = 100
for proc_name in missing:
    team = team_assign.get(proc_name, '前段')
    proc_code = f'AUTO-{code_counter}'
    code_counter += 1
    c.execute('INSERT OR IGNORE INTO processes (process_code, process_name, team_name) VALUES (?,?,?)',
              (proc_code, proc_name, team))
    print(f'Added: {proc_code} | {proc_name} | {team}')

conn.commit()

# Now create process_equipment mappings for new processes
c.execute('SELECT id, process_code, process_name, team_name FROM processes WHERE process_code LIKE ?', ('AUTO-%',))
new_procs = c.fetchall()
c.execute('SELECT id, team_id FROM equipments')
eq_by_team = {}
for eq in c.fetchall():
    eq_by_team.setdefault(eq[1], []).append(eq[0])

mapped = 0
for pc_id, pc_code, pc_name, team_name in new_procs:
    team_map = {'前段': 1, '焊接': 2, '扣压': 3, '装配包装': 4}
    tid = team_map.get(team_name, 1)
    if tid in eq_by_team:
        for eq_id in eq_by_team[tid][:3]:  # Map to first 3 equipment
            c.execute('INSERT OR IGNORE INTO process_equipment (process_code, equipment_id, is_primary) VALUES (?,?,1)',
                      (pc_code, eq_id))
            mapped += 1

conn.commit()
conn.close()
print(f'Done. Mapped {mapped} process-equipment links.')
