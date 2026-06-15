# -*- coding: utf-8 -*-
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "production.db")

def check_products_data():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute("SELECT * FROM products LIMIT 5")
    products = c.fetchall()
    
    print(f"products 表中共有 {len(products)} 条记录")
    for p in products:
        print(f"  {p}")
    
    conn.close()

if __name__ == "__main__":
    check_products_data()
