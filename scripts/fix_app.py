# -*- coding: utf-8 -*-
import os

p = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'app.py')
with open(p, 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace('process_code team_name', 'process_code, team_name')
content = content.replace('e.id e.equipment_code', 'e.id, e.equipment_code')
content = content.replace('e.equipment_code e.equipment_name', 'e.equipment_code, e.equipment_name')
content = content.replace('e.equipment_name e.equipment_type', 'e.equipment_name, e.equipment_type')
content = content.replace('e.equipment_type e.capacity_per_hour', 'e.equipment_type, e.capacity_per_hour')
content = content.replace('e.capacity_per_hour e.location', 'e.capacity_per_hour, e.location')
content = content.replace('LIMIT 20,', 'LIMIT 20"',')

with open(p, 'w', encoding='utf-8') as f:
    f.write(content)
print('Fixed app.py')