# -*- coding: utf-8 -*-
import os

path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'templates', 'schedule.html')
content = open(path, 'r', encoding='utf-8').read()

# Show what's corrupted around key areas
for keyword in ['process-select', 'equipment-select', 'order-search']:
    idx = content.find(keyword)
    if idx > 0:
        snippet = content[max(0,idx-80):idx+80]
        print(f"Around '{keyword}':")
        for i, ch in enumerate(snippet):
            if ord(ch) > 127:
                print(f"  char at {i}: U+{ord(ch):04X} = {ch!r}")
        print()

print("Total length:", len(content))
