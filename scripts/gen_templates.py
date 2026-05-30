# -*- coding: utf-8 -*-
import os

TPL = os.path.join(os.getcwd(), 'templates')

def w(name, content):
    path = os.path.join(TPL, name)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f'Created {name}')

print('Starting template generation...')