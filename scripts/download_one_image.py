# -*- coding: utf-8 -*-
import sqlite3
import os
import requests

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "production.db")
IMAGES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "images", "products")

def download_one_image():
    """下载一个产品图片作为测试"""
    os.makedirs(IMAGES_DIR, exist_ok=True)
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    # 查询第一个有图片URL的产品
    c.execute("SELECT id, product_code, image_url FROM products WHERE image_url IS NOT NULL AND image_url != '' LIMIT 1")
    product = c.fetchone()
    
    if not product:
        print("没有找到有图片URL的产品")
        return
    
    product_id = product['id']
    product_code = product['product_code']
    image_url = product['image_url']
    
    print(f"产品编码: {product_code}")
    print(f"图片URL: {image_url}")
    
    # 生成文件名
    safe_code = product_code.replace('/', '_').replace('\\', '_').replace(':', '_').replace('.', '_')
    ext = '.jpg'
    if '.png' in image_url.lower():
        ext = '.png'
    
    filename = f"{safe_code}{ext}"
    filepath = os.path.join(IMAGES_DIR, filename)
    
    print(f"保存路径: {filepath}")
    
    # 下载图片
    try:
        response = requests.get(image_url, timeout=30)
        response.raise_for_status()
        
        with open(filepath, 'wb') as f:
            f.write(response.content)
        
        # 更新数据库
        image_path = f"/static/images/products/{filename}"
        c.execute("UPDATE products SET image_path=? WHERE id=?", (image_path, product_id))
        conn.commit()
        
        print(f"下载成功: {len(response.content)} 字节")
        print(f"数据库已更新: image_path = {image_path}")
        
    except Exception as e:
        print(f"下载失败: {e}")
    
    conn.close()

if __name__ == "__main__":
    download_one_image()
