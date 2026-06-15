# -*- coding: utf-8 -*-
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "production.db")
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

# 统计有image_path的产品数量
c.execute("SELECT COUNT(*) FROM products WHERE image_path IS NOT NULL AND image_path != ''")
count = c.fetchone()[0]
print(f"有image_path的产品数量: {count}")

# 统计有image_url的产品数量
c.execute("SELECT COUNT(*) FROM products WHERE image_url IS NOT NULL AND image_url != ''")
count = c.fetchone()[0]
print(f"有image_url的产品数量: {count}")

conn.close()
