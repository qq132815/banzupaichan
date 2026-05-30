# -*- coding: utf-8 -*-
import os

# Add auto-fix missing processes to rebuild_all.py
rb_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'scripts', 'rebuild_all.py')
c = open(rb_path, 'r', encoding='utf-8').read()

# Add after the route import section
old = "    print('Process routes imported: ' + str(count))"
new = """    print('Process routes imported: ' + str(count))
    # Auto-add missing process names from routes
    c.execute("SELECT process_list FROM process_routes WHERE process_list IS NOT NULL AND process_list != ''")
    all_procs = set()
    for r in c.fetchall():
        for p in r[0].split(','):
            p = p.strip()
            if p: all_procs.add(p)
    c.execute("SELECT process_name FROM processes")
    existing = set(r[0] for r in c.fetchall())
    missing = all_procs - existing
    team_map2 = {}
    c.execute("SELECT route_code, process_list FROM process_routes")
    for r in c.fetchall():
        rc = r[0] or ''
        pl = r[1] or ''
        t = '\\u524d\\u6bb5' if '\\u524d\\u6bb5' in rc else '\\u710a\\u63a5' if '\\u710a\\u63a5' in rc else '\\u6263\\u538b' if '\\u6263\\u538b' in rc else '\\u88c5\\u914d\\u5305\\u88c5'
        for p in pl.split(','):
            p = p.strip()
            if p and p not in team_map2: team_map2[p] = t
    cnt2 = 200
    for pn in missing:
        tm = team_map2.get(pn, '\\u88c5\\u914d\\u5305\\u88c5')
        c.execute("INSERT OR IGNORE INTO processes (process_code, process_name, team_name) VALUES (?,?,?)", (f'NEW-{cnt2}', pn, tm))
        cnt2 += 1
    if missing:
        c.execute("SELECT id, team_id FROM equipments")
        eqbt = {}
        for eq in c.fetchall(): eqbt.setdefault(eq[1], []).append(eq[0])
        c.execute("SELECT process_code, team_name FROM processes WHERE process_code LIKE 'NEW-%'")
        tmap = {'\\u524d\\u6bb5':1,'\\u710a\\u63a5':2,'\\u6263\\u538b':3,'\\u88c5\\u914d\\u5305\\u88c5':4}
        for pc_code, tn in c.fetchall():
            tid = tmap.get(tn, 4)
            if tid in eqbt:
                for eq_id in eqbt[tid][:3]:
                    c.execute("INSERT OR IGNORE INTO process_equipment (process_code, equipment_id, is_primary) VALUES (?,?,1)", (pc_code, eq_id))
        print(f'Auto-added {len(missing)} missing processes')"""

c = c.replace(old, new)
open(rb_path, 'w', encoding='utf-8').write(c)
print('rebuild_all.py updated with auto-fix')
