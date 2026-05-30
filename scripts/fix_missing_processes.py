# -*- coding: utf-8 -*-
import sqlite3, os

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'production.db')
conn = sqlite3.connect(DB)
c = conn.cursor()

# Get all unique process names from routes
c.execute("SELECT process_list FROM process_routes WHERE process_list IS NOT NULL AND process_list != ''")
all_procs = set()
for r in c.fetchall():
    for p in r[0].split(','):
        p = p.strip()
        if p:
            all_procs.add(p)

# Get existing process names
c.execute("SELECT process_name FROM processes")
existing = set(r[0] for r in c.fetchall())

# Find missing
missing = all_procs - existing
print(f"Total unique process names: {len(all_procs)}")
print(f"Existing: {len(existing)}")
print(f"Missing: {len(missing)}")

# Insert missing with default team assignment
counter = 200
team_map = {}
# Read routes to determine team assignments
c.execute("SELECT product_code, route_code, process_list FROM process_routes")
for r in c.fetchall():
    route_code = r[1] or ''
    proc_list = r[2] or ''
    if '前段' in route_code:
        team = '前段'
    elif '焊接' in route_code:
        team = '焊接'
    elif '扣压' in route_code:
        team = '扣压'
    elif '装配' in route_code or '总装' in route_code:
        team = '装配包装'
    else:
        team = '装配包装'
    for p in proc_list.split(','):
        p = p.strip()
        if p and p not in team_map:
            team_map[p] = team

for proc_name in missing:
    team = team_map.get(proc_name, '装配包装')
    proc_code = f'NEW-{counter}'
    counter += 1
    c.execute("INSERT OR IGNORE INTO processes (process_code, process_name, team_name) VALUES (?,?,?)",
              (proc_code, proc_name, team))

conn.commit()

# Create equipment mappings for new processes
c.execute("SELECT id, process_code, process_name, team_name FROM processes WHERE process_code LIKE 'NEW-%'")
new_procs = c.fetchall()
c.execute("SELECT id, team_id FROM equipments")
eq_by_team = {}
for eq in c.fetchall():
    eq_by_team.setdefault(eq[1], []).append(eq[0])

tmap = {'前段': 1, '焊接': 2, '扣压': 3, '装配包装': 4}
mapped = 0
for _, pc_code, pc_name, team_name in new_procs:
    tid = tmap.get(team_name, 4)
    if tid in eq_by_team:
        for eq_id in eq_by_team[tid][:3]:
            c.execute("INSERT OR IGNORE INTO process_equipment (process_code, equipment_id, is_primary) VALUES (?,?,1)",
                      (pc_code, eq_id))
            mapped += 1

conn.commit()
conn.close()
print(f"Added {len(missing)} missing processes, mapped {mapped} equipment links")
