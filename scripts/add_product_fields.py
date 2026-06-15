# -*- coding: utf-8 -*-
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "production.db")

def add_product_image_fields():
    """为products表添加图片相关字段"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # 检查字段是否已存在
    c.execute("PRAGMA table_info(products)")
    columns = [col[1] for col in c.fetchall()]
    
    # 添加新字段
    new_fields = [
        ("image_url", "TEXT"),
        ("image_path", "TEXT"),
        ("specifications", "TEXT"),
        ("description", "TEXT"),
        ("category", "TEXT"),
        ("customer", "TEXT"),
        ("project", "TEXT"),
        ("status", "TEXT DEFAULT 'active'"),
        ("created_at", "TEXT DEFAULT (datetime('now','localtime'))"),
        ("updated_at", "TEXT DEFAULT (datetime('now','localtime'))")
    ]
    
    for field_name, field_type in new_fields:
        if field_name not in columns:
            try:
                c.execute(f"ALTER TABLE products ADD COLUMN {field_name} {field_type}")
                print(f"添加字段: {field_name}")
            except sqlite3.OperationalError as e:
                print(f"字段 {field_name} 可能已存在: {e}")
    
    # 创建图片存储目录
    images_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "images", "products")
    os.makedirs(images_dir, exist_ok=True)
    print(f"图片目录已创建: {images_dir}")
    
    conn.commit()
    conn.close()
    print("数据库表结构更新完成")

if __name__ == "__main__":
    add_product_image_fields()
