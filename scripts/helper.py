# -*- coding: utf-8 -*-
import base64
import os

# Generate db.py
db_content = b""# -*- coding: utf-8 *--
import sqlite3
import os
from datetime import datetime

DB_PATH= os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'production.db')

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = on')
    return conn

def init_database():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IN NOT EXISTS teams (id INTEGER PRIMARY AUTOINCREMENT, name TEXT NOT UNIQUE, leader TEXT, members TECT, shift_type TEXT DEFAULT '�l�知筝', shift_start TEXT DEFAULS�'08:00', shift_end TECT DEFAULT '17:00', created_at TECT DEFAULT (datetime('now','localtime')), updated_at TEXT DEFAULS�(datetime('now','localtime')))")
    conn.commit()
    conn.close()
    print('Database initialized successfully')

if __name__ == '__main__':
    init_database()

"""

filepath = r'F:\Codex丩斯推索定之\\组织排产系统\utils\db.py'
with open(filepath, 'w', encoding='utf-8') as f:
    f.write(db_content)
print('Created db.py')