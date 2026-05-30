# -*- coding: utf-8 -*-
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.db import get_connection

conn = get_connection()
c = conn.cursor()

for pc in ['G002773', 'F26-8108010HV', 'F26-8108010HV-\u7ec4\u4ef66-\u710a\u63a5']:
    c.execute("SELECT route_code, route_name, process_list FROM process_routes WHERE product_code = ?", (pc,))
    routes = c.fetchall()
    count = 0
    for r in routes:
        if r[2]:
            for p in r[2].split(','):
                p = p.strip()
                if p:
                    c.execute("SELECT process_code FROM processes WHERE process_name=?", (p,))
                    if c.fetchone():
                        count += 1
    print(f"{pc}: {len(routes)} routes, {count} process matches")

conn.close()
