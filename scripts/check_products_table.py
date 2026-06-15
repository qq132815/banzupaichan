# -*- coding: utf-8 -*-
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "production.db")

def check_products_table():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute("PRAGMA table_info(products)")
    columns = c.fetchall()
    
    print("products 表结构:")
    for col in columns:
        print(f"  {col[1]} - {col[2]}")
    
    conn.close()

if __name__ == "__main__":
    check_products_table()
