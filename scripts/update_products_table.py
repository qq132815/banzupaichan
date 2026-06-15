# -*- coding: utf-8 -*-
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "production.db")

def update_products_table():
    """更新products表结构，添加新字段"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # 检查字段是否已存在
    c.execute("PRAGMA table_info(products)")
    columns = [col[1] for col in c.fetchall()]
    
    # 添加新字段
    new_fields = [
        ("product_type", "TEXT"),
        ("unit", "TEXT"),
        ("route_code", "TEXT"),
        ("stock_qty", "REAL DEFAULT 0"),
        ("source", "TEXT"),
        ("basket_capacity", "REAL DEFAULT 0")
    ]
    
    for field_name, field_type in new_fields:
        if field_name not in columns:
            try:
                c.execute(f"ALTER TABLE products ADD COLUMN {field_name} {field_type}")
                print(f"添加字段: {field_name}")
            except sqlite3.OperationalError as e:
                print(f"字段 {field_name} 可能已存在: {e}")
    
    conn.commit()
    conn.close()
    print("数据库表结构更新完成")

if __name__ == "__main__":
    update_products_table()
