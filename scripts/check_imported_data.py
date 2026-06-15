# -*- coding: utf-8 -*-
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "production.db")

def check_imported_data():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    # 统计总数
    c.execute("SELECT COUNT(*) as total FROM products")
    total = c.fetchone()['total']
    print(f"产品总数: {total}")
    
    # 统计有图片URL的产品
    c.execute("SELECT COUNT(*) as count FROM products WHERE image_url IS NOT NULL AND image_url != ''")
    with_image_url = c.fetchone()['count']
    print(f"有图片URL的产品: {with_image_url}")
    
    # 统计有本地图片的产品
    c.execute("SELECT COUNT(*) as count FROM products WHERE image_path IS NOT NULL AND image_path != ''")
    with_image_path = c.fetchone()['count']
    print(f"有本地图片的产品: {with_image_path}")
    
    # 按产品类型统计
    c.execute("SELECT product_type, COUNT(*) as count FROM products GROUP BY product_type ORDER BY count DESC")
    types = c.fetchall()
    print(f"\n产品类型分布:")
    for t in types:
        print(f"  {t['product_type'] or '未分类'}: {t['count']}")
    
    # 按客户统计（前10）
    c.execute("SELECT customer, COUNT(*) as count FROM products WHERE customer IS NOT NULL AND customer != '' GROUP BY customer ORDER BY count DESC LIMIT 10")
    customers = c.fetchall()
    print(f"\n前10客户:")
    for c in customers:
        print(f"  {c['customer']}: {c['count']}")
    
    conn.close()

if __name__ == "__main__":
    check_imported_data()
